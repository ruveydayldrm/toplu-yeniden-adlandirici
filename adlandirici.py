#!/usr/bin/env python3
"""Toplu Yeniden Adlandırıcı — bir klasördeki dosyaları tarihe ya da bir kalıba göre yeniden adlandırır.

Kullanım:
    python adlandirici.py Fotograflar --tarih            # 2024-02-10_001.jpg, 2024-02-10_002.jpg ...
    python adlandirici.py Fotograflar --kalip "tatil_{n:03}"
    python adlandirici.py Fotograflar --tarih --dene     # Önce bir bakalım
    python adlandirici.py Fotograflar --geri-al          # Son işlemi geri al
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

GUNLUK = ".adlandirici-gunluk.json"
YASAK_KARAKTERLER = set('<>:"/\\|?*')


# --- Fotoğraf tarihi (EXIF) --------------------------------------------------

def exif_tarihi(yol: Path) -> datetime | None:
    """JPEG dosyasının EXIF bilgisinden çekim tarihini okur; bulamazsa None döner."""
    try:
        with open(yol, "rb") as f:
            if f.read(2) != b"\xff\xd8":
                return None
            while True:
                isaret = f.read(2)
                if len(isaret) < 2 or isaret[0] != 0xFF or isaret[1] in (0xD9, 0xDA):
                    return None
                uzunluk = int.from_bytes(f.read(2), "big")
                veri = f.read(uzunluk - 2)
                if isaret[1] == 0xE1 and veri.startswith(b"Exif\x00\x00"):
                    return _tiff_tarihi(veri[6:])
    except (OSError, ValueError, IndexError, UnicodeDecodeError):
        return None


def _tiff_tarihi(t: bytes) -> datetime | None:
    sira = {b"II": "little", b"MM": "big"}.get(t[:2])
    if sira is None:
        return None

    def u16(o):
        return int.from_bytes(t[o:o + 2], sira)

    def u32(o):
        return int.from_bytes(t[o:o + 4], sira)

    def etiketler(ofset):
        # Her girdi: etiket (2), tip (2), adet (4), değer/ofset (4)
        sonuc = {}
        for i in range(u16(ofset)):
            g = ofset + 2 + i * 12
            if g + 12 > len(t):
                break
            sonuc[u16(g)] = (u16(g + 2), u32(g + 4), g + 8)
        return sonuc

    def metin(girdi):
        tip, adet, g = girdi
        if tip != 2:  # ASCII
            return None
        bas = g if adet <= 4 else u32(g)
        return t[bas:bas + adet].rstrip(b"\x00").decode("ascii", "ignore")

    ifd0 = etiketler(u32(4))
    adaylar = []
    if 0x8769 in ifd0:  # Exif alt dizini
        exif = etiketler(u32(ifd0[0x8769][2]))
        adaylar += [exif.get(0x9003), exif.get(0x9004)]  # DateTimeOriginal, DateTimeDigitized
    adaylar.append(ifd0.get(0x0132))  # DateTime
    for girdi in adaylar:
        if girdi:
            try:
                return datetime.strptime((metin(girdi) or "")[:19], "%Y:%m:%d %H:%M:%S")
            except ValueError:
                continue
    return None


def dosya_tarihi(yol: Path) -> datetime:
    """Önce EXIF çekim tarihini, yoksa dosyanın değiştirilme tarihini kullanır."""
    return exif_tarihi(yol) or datetime.fromtimestamp(yol.stat().st_mtime)


# --- Plan --------------------------------------------------------------------

def dosyalari_bul(klasor: Path, uzantilar: set[str] | None = None) -> list[Path]:
    """Gizli dosyalar ve alt klasörler hariç, ada göre sıralı dosya listesi."""
    return sorted(
        (p for p in klasor.iterdir()
         if p.is_file() and not p.name.startswith(".")
         and (not uzantilar or p.suffix.lower() in uzantilar)),
        key=lambda p: p.name.lower(),
    )


def tarihe_gore_plan(dosyalar: list[Path]) -> list[tuple[Path, str]]:
    """Dosyaları çekim zamanına göre sıralayıp her gün için 001'den numaralar."""
    tarihli = sorted(((dosya_tarihi(p), p) for p in dosyalar), key=lambda x: (x[0], x[1].name.lower()))
    sayac: dict[str, int] = {}
    plan = []
    for tarih, p in tarihli:
        gun = tarih.strftime("%Y-%m-%d")
        sayac[gun] = sayac.get(gun, 0) + 1
        plan.append((p, f"{gun}_{sayac[gun]:03d}{p.suffix.lower()}"))
    return plan


def kaliba_gore_plan(dosyalar: list[Path], kalip: str, baslangic: int = 1) -> list[tuple[Path, str]]:
    """Kalıpta {n} (sıra no), {ad} (eski ad) ve {tarih} (YYYY-AA-GG) kullanılabilir."""
    plan = []
    for n, p in enumerate(dosyalar, start=baslangic):
        tarih = dosya_tarihi(p).strftime("%Y-%m-%d") if "{tarih" in kalip else ""
        try:
            govde = kalip.format(n=n, ad=p.stem, tarih=tarih)
        except (KeyError, IndexError, ValueError) as h:
            raise ValueError(f"Geçersiz kalıp {kalip!r}: {h}") from None
        if not govde.strip() or YASAK_KARAKTERLER & set(govde):
            raise ValueError(f"Kalıp geçersiz bir dosya adı üretti: {govde!r}")
        plan.append((p, govde + p.suffix.lower()))
    return plan


def cakismalari_coz(plan: list[tuple[Path, str]]) -> list[tuple[Path, Path]]:
    """Hedef adları kesinleştirir: aynı ada düşen ya da klasörde zaten var olan
    adlara ' (1)', ' (2)' ekler; adı değişmeyecek dosyaları çıkarır."""
    if not plan:
        return []
    klasor = plan[0][0].parent
    kaynaklar = {p.name.lower() for p, _ in plan}
    alinan: set[str] = set()
    sonuc = []
    for kaynak, ad in plan:
        govde, uzanti = os.path.splitext(ad)
        hedef, sayi = ad, 1
        while hedef.lower() in alinan or (hedef.lower() not in kaynaklar and (klasor / hedef).exists()):
            hedef = f"{govde} ({sayi}){uzanti}"
            sayi += 1
        alinan.add(hedef.lower())
        if hedef != kaynak.name:
            sonuc.append((kaynak, kaynak.with_name(hedef)))
    return sonuc


# --- Uygulama ve geri alma ---------------------------------------------------

def _tasi(ciftler: list[tuple[Path, Path]]) -> None:
    """İki aşamalı taşıma: önce geçici adlara, sonra hedeflere. Böylece a→b, b→a
    gibi yer değiştirmeler de sorunsuz olur. Hata çıkarsa yapılanları geri alır."""
    yapilan: list[tuple[Path, Path]] = []
    try:
        gecici = []
        for i, (kaynak, hedef) in enumerate(ciftler):
            ara = kaynak.with_name(f".adlandirici-{os.getpid()}-{i}.tmp")
            kaynak.rename(ara)
            yapilan.append((ara, kaynak))
            gecici.append((ara, hedef))
        for ara, hedef in gecici:
            ara.rename(hedef)
            yapilan.append((hedef, ara))
    except OSError:
        for simdiki, onceki in reversed(yapilan):
            simdiki.rename(onceki)
        raise


def uygula(klasor: Path, degisiklikler: list[tuple[Path, Path]]) -> None:
    _tasi(degisiklikler)
    kayit = [{"eski": k.name, "yeni": h.name} for k, h in degisiklikler]
    (klasor / GUNLUK).write_text(json.dumps(kayit, ensure_ascii=False, indent=2), encoding="utf-8")


def geri_al(klasor: Path) -> list[tuple[Path, Path]]:
    gunluk = klasor / GUNLUK
    if not gunluk.exists():
        raise FileNotFoundError("Geri alınacak bir işlem bulunamadı.")
    kayit = json.loads(gunluk.read_text(encoding="utf-8"))
    ciftler = [(klasor / k["yeni"], klasor / k["eski"]) for k in kayit if (klasor / k["yeni"]).exists()]
    _tasi(ciftler)
    gunluk.unlink()
    return ciftler


# --- Komut satırı ------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="adlandirici", description="Dosyaları toplu olarak yeniden adlandırır.")
    p.add_argument("klasor", nargs="?", default=".", help="Dosyaların bulunduğu klasör (varsayılan: bulunulan klasör)")
    mod = p.add_mutually_exclusive_group()
    mod.add_argument("--tarih", action="store_true", help="Çekim/değiştirilme tarihine göre: 2024-02-10_001.jpg")
    mod.add_argument("--kalip", help='Örn: "tatil_{n:03}" veya "{tarih}_{ad}"')
    mod.add_argument("--geri-al", action="store_true", help="Son yeniden adlandırmayı geri al")
    p.add_argument("--uzanti", help="Yalnızca bu uzantılar, örn: .jpg,.png")
    p.add_argument("--baslangic", type=int, default=1, help="Kalıpta {n} için başlangıç numarası")
    p.add_argument("--dene", action="store_true", help="Hiçbir şeyi değiştirmeden ne olacağını göster")
    args = p.parse_args(argv)

    klasor = Path(args.klasor).expanduser()
    if not klasor.is_dir():
        print(f"Klasör bulunamadı: {klasor}", file=sys.stderr)
        return 1

    try:
        if args.geri_al:
            for simdiki, eski in geri_al(klasor):
                print(f"  {simdiki.name}  →  {eski.name}")
            print("\nSon işlem geri alındı.")
            return 0

        if not (args.tarih or args.kalip):
            p.error("--tarih, --kalip ya da --geri-al seçeneklerinden birini verin.")

        uzantilar = None
        if args.uzanti:
            uzantilar = {("." + u.strip().lstrip(".")).lower() for u in args.uzanti.split(",") if u.strip()}
        dosyalar = dosyalari_bul(klasor, uzantilar)
        plan = tarihe_gore_plan(dosyalar) if args.tarih else kaliba_gore_plan(dosyalar, args.kalip, args.baslangic)
        degisiklikler = cakismalari_coz(plan)
    except (ValueError, OSError) as h:
        print(f"Hata: {h}", file=sys.stderr)
        return 1

    if not degisiklikler:
        print("Yeniden adlandırılacak dosya yok.")
        return 0
    for kaynak, hedef in degisiklikler:
        print(f"  {kaynak.name}  →  {hedef.name}")

    if args.dene:
        print(f"\n(Deneme) {len(degisiklikler)} dosya yeniden adlandırılacaktı. Hiçbir şey değişmedi.")
        return 0
    try:
        uygula(klasor, degisiklikler)
    except OSError as h:
        print(f"Hata, hiçbir dosya değiştirilmedi: {h}", file=sys.stderr)
        return 1
    print(f"\n{len(degisiklikler)} dosya yeniden adlandırıldı. Geri almak için: python adlandirici.py \"{args.klasor}\" --geri-al")
    return 0


if __name__ == "__main__":
    sys.exit(main())
