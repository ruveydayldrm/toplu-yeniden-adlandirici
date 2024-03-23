# Toplu Yeniden Adlandırıcı 🏷️

Bir klasördeki dosyaları tek komutla yeniden adlandıran küçük bir Python aracı. Fotoğrafları çekildikleri tarihe göre sıralamak için idealdir.

```
IMG_4821.JPG   →  2024-02-10_001.jpg
IMG_4822.JPG   →  2024-02-10_002.jpg
DSC_0007.jpg   →  2024-02-11_001.jpg
```

## Özellikler

- **Tarihe göre** (`--tarih`): Fotoğrafın EXIF bilgisindeki çekim tarihini okur, yoksa dosyanın değiştirilme tarihini kullanır. Her gün 001'den numaralanır.
- **Kalıba göre** (`--kalip`): `{n}` sıra numarası, `{ad}` eski ad, `{tarih}` YYYY-AA-GG. Örn: `"tatil_{n:03}"` → `tatil_001.jpg`
- **Deneme modu** (`--dene`): hiçbir dosyayı değiştirmeden ne olacağını gösterir.
- **Geri alma** (`--geri-al`): son işlemi tamamen geri alır.
- **Üzerine yazmaz**: aynı ad varsa `ad (1).jpg` olarak adlandırır.
- Gizli dosyalara ve alt klasörlere dokunmaz.
- Ek kütüphane gerektirmez (EXIF okuyucu dahili); yalnızca Python 3.9+.

## Kullanım

```bash
python adlandirici.py Fotograflar --tarih --dene        # Önce bir bakalım
python adlandirici.py Fotograflar --tarih
python adlandirici.py Fotograflar --kalip "tatil_{n:03}" --uzanti .jpg,.png
python adlandirici.py Belgeler --kalip "{tarih}_{ad}"
python adlandirici.py Fotograflar --kalip "foto_{n}" --baslangic 100
python adlandirici.py Fotograflar --geri-al
```

## Testler

```bash
python -m unittest -v
```
