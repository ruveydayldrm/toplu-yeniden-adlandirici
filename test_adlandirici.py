import contextlib
import io
import os
import struct
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import adlandirici


def exifli_jpeg(tarih: str) -> bytes:
    """DateTimeOriginal etiketi içeren en küçük geçerli JPEG başlığını üretir."""
    deger = tarih.encode("ascii") + b"\x00"
    tiff = b"MM" + struct.pack(">HI", 42, 8)
    tiff += struct.pack(">H", 1) + struct.pack(">HHII", 0x8769, 4, 1, 26) + struct.pack(">I", 0)
    tiff += struct.pack(">H", 1) + struct.pack(">HHII", 0x9003, 2, len(deger), 44) + struct.pack(">I", 0)
    tiff += deger
    app1 = b"Exif\x00\x00" + tiff
    return b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xd9"


class KlasorTesti(unittest.TestCase):
    def setUp(self):
        self._gecici = tempfile.TemporaryDirectory()
        self.klasor = Path(self._gecici.name)

    def tearDown(self):
        self._gecici.cleanup()

    def dosya(self, ad, icerik=b"x", zaman=None):
        yol = self.klasor / ad
        yol.write_bytes(icerik)
        if zaman:
            ts = zaman.timestamp()
            os.utime(yol, (ts, ts))
        return yol

    def adlar(self):
        return sorted(p.name for p in self.klasor.iterdir())


class ExifTesti(KlasorTesti):
    def test_cekim_tarihi_okunur(self):
        yol = self.dosya("foto.jpg", exifli_jpeg("2024:02:10 14:30:00"))
        self.assertEqual(adlandirici.exif_tarihi(yol), datetime(2024, 2, 10, 14, 30))

    def test_exif_yoksa_none(self):
        self.assertIsNone(adlandirici.exif_tarihi(self.dosya("a.jpg", b"\xff\xd8\xff\xd9")))
        self.assertIsNone(adlandirici.exif_tarihi(self.dosya("b.txt", b"merhaba")))
        self.assertIsNone(adlandirici.exif_tarihi(self.dosya("c.jpg", b"\xff\xd8\xff\xe1\x00")))

    def test_exif_yoksa_degistirilme_tarihi(self):
        yol = self.dosya("not.txt", zaman=datetime(2023, 5, 1, 9, 0))
        self.assertEqual(adlandirici.dosya_tarihi(yol), datetime(2023, 5, 1, 9, 0))


class PlanTesti(KlasorTesti):
    def test_tarihe_gore_gun_gun_numaralar(self):
        self.dosya("IMG_9.JPG", exifli_jpeg("2024:02:10 18:00:00"))
        self.dosya("IMG_1.jpg", exifli_jpeg("2024:02:10 09:00:00"))
        self.dosya("IMG_5.jpg", exifli_jpeg("2024:02:11 12:00:00"))
        plan = adlandirici.tarihe_gore_plan(adlandirici.dosyalari_bul(self.klasor))
        self.assertEqual([(k.name, h) for k, h in plan], [
            ("IMG_1.jpg", "2024-02-10_001.jpg"),
            ("IMG_9.JPG", "2024-02-10_002.jpg"),
            ("IMG_5.jpg", "2024-02-11_001.jpg"),
        ])

    def test_kalip(self):
        self.dosya("b.png")
        self.dosya("a.png")
        plan = adlandirici.kaliba_gore_plan(adlandirici.dosyalari_bul(self.klasor), "tatil_{n:03}_{ad}", 7)
        self.assertEqual([h for _, h in plan], ["tatil_007_a.png", "tatil_008_b.png"])

    def test_gecersiz_kalip(self):
        dosyalar = [self.dosya("a.txt")]
        for kalip in ["{yok}", "a/{n}", "{n:zz}"]:
            with self.subTest(kalip=kalip), self.assertRaises(ValueError):
                adlandirici.kaliba_gore_plan(dosyalar, kalip)

    def test_uzanti_suzgeci_ve_gizli_dosyalar(self):
        self.dosya("a.jpg")
        self.dosya("b.txt")
        self.dosya(".gizli.jpg")
        bulunan = adlandirici.dosyalari_bul(self.klasor, {".jpg"})
        self.assertEqual([p.name for p in bulunan], ["a.jpg"])

    def test_cakisan_adlar_numaralanir(self):
        a, b = self.dosya("a.txt"), self.dosya("b.txt")
        self.dosya("sabit.txt")  # planda olmayan ama hedefi işgal eden dosya
        sonuc = adlandirici.cakismalari_coz([(a, "sabit.txt"), (b, "sabit.txt")])
        self.assertEqual([h.name for _, h in sonuc], ["sabit (1).txt", "sabit (2).txt"])

    def test_adi_degismeyen_dosya_atlanir(self):
        a = self.dosya("x_001.txt")
        self.assertEqual(adlandirici.cakismalari_coz([(a, "x_001.txt")]), [])


class UygulamaTesti(KlasorTesti):
    def calistir(self, *argumanlar):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return adlandirici.main([str(self.klasor), *argumanlar])

    def test_yer_degistirme(self):
        a, b = self.dosya("a.txt", b"A"), self.dosya("b.txt", b"B")
        adlandirici.uygula(self.klasor, [(a, b), (b, a)])
        self.assertEqual(a.read_bytes(), b"B")
        self.assertEqual(b.read_bytes(), b"A")

    def test_uygula_ve_geri_al(self):
        self.dosya("kedi.jpg", b"1")
        self.dosya("kopek.jpg", b"2")
        self.assertEqual(self.calistir("--kalip", "hayvan_{n}"), 0)
        self.assertEqual(self.adlar(), [adlandirici.GUNLUK, "hayvan_1.jpg", "hayvan_2.jpg"])
        self.assertEqual((self.klasor / "hayvan_1.jpg").read_bytes(), b"1")

        self.assertEqual(self.calistir("--geri-al"), 0)
        self.assertEqual(self.adlar(), ["kedi.jpg", "kopek.jpg"])

    def test_deneme_modu_dokunmaz(self):
        self.dosya("a.txt")
        self.assertEqual(self.calistir("--kalip", "yeni_{n}", "--dene"), 0)
        self.assertEqual(self.adlar(), ["a.txt"])

    def test_geri_alinacak_islem_yoksa_hata(self):
        self.assertEqual(self.calistir("--geri-al"), 1)


if __name__ == "__main__":
    unittest.main()
