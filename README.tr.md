# trackpad-like-mac

Linux touchpad'ini MacBook trackpad'i gibi kullan: üç parmakla sürükleme,
Mac hareketleri ve parmağına yapışık kaydırma.

[English](README.md)

## Neler var

| Hareket | Ne yapar |
|---|---|
| Üç parmakla sürükle | Pencere, dosya ve metin seçimi sürükler (macOS'taki "üç parmakla sürükleme") |
| Dört parmak sağa / sola | Masaüstleri arası geçiş |
| Dört parmak yukarı / aşağı | Tüm pencereler görünümü (Mission Control benzeri) |
| Başparmak + üç parmakla kıstır | Uygulama listesi (Launchpad), parmağını takip ederek açılır |
| Başparmak + üç parmakla aç | Pencereler kenara kayar, masaüstü görünür; kıstırınca geri gelir |
| Sağ kenardan iki parmakla içeri kaydır | Bildirimler açılır; sağa kaydırınca kapanır |
| İki parmakla kaydır | Yavaşta içerik parmağın kadar gider, hızlı fırlatınca hızlanır |
| Dokun | Tıklama (dokunup sürükleme kapalı, tıklarken yanlışlıkla sürüklemez) |
| İki parmakla bas ya da dokun | Sağ tık |

Animasyonlar parmağını takip eder; erken bırakırsan Mac'teki gibi geri döner.

## Kurulum

Kurduktan sonra oturumu bir kez kapatıp aç.

**Tek satır** (Ubuntu, Debian ve diğer dağıtımlar):

```bash
curl -fsSL https://raw.githubusercontent.com/beylerburak/trackpad-like-mac/main/scripts/get.sh | bash
```

Son sürümü indirir, doğrular ve kurar: Debian/Ubuntu'da (amd64) `.deb`
paketi olarak, diğerlerinde kaynak koddan.

**Paket** (Ubuntu/Debian):
[Son sürümden](https://github.com/beylerburak/trackpad-like-mac/releases/latest)
`.deb` dosyasını indir ve şunu çalıştır:

```bash
sudo apt install ./trackpad-like-mac_*_amd64.deb
```

**Kaynak koddan** (`make`, C derleyicisi ve Python 3 gerekir):

```bash
git clone https://github.com/beylerburak/trackpad-like-mac.git
cd trackpad-like-mac
./install.sh
```

## Gereksinimler

- systemd ve Python 3.9+ kullanan bir Linux
- Üç parmak sürükleme dışındaki her şey için GNOME Shell 45–48 (sürükleme
  her masaüstünde çalışır)
- Mac'teki gibi kaydırma için Wayland oturumu
- En az dört parmağı algılayan bir touchpad (çoğu algılar; `trackpad-like-mac status`)

Ubuntu 24.04, GNOME 46, Wayland üzerinde geliştirildi ve test edildi.

## Kullanım

```bash
trackpad-like-mac status     # neler çalışıyor
trackpad-like-mac reset      # senin kullanıcın için kapat, eski touchpad ayarlarını geri yükle
trackpad-like-mac setup      # tekrar aç
trackpad-like-mac uninstall  # sıfırla ve tamamen kaldır
```

Her kullanıcı ilk girişinde otomatik ayarlanır. Sonradan GNOME Ayarlar'da
yaptığın değişiklikler korunur.

## Ayarlar

- `/etc/trackpad-like-mac.conf`: sürükleme hızı, parmakları kaldırınca
  sürüklemenin ne kadar bekleyeceği ve başlaması için gereken hareket.
  Uygulamak için: `sudo systemctl restart trackpad-like-mac`.
- `~/.config/trackpad-like-mac/scroll.conf`: kaydırma, anında uygulanır.
  `slow` ve `fast`, yavaş kaydırırken ve fırlatırken parmağın her milimetresinde
  içeriğin kaç milimetre gideceğini belirler. `px_per_mm` her girişte
  ekranından ölçülür.

## Nasıl çalışır

- **Küçük bir servis** (`trackpad-like-mac-daemon`, Python, yalnızca standart
  kütüphane) touchpad'i kilitlemeden okur. Üç parmak hareket edince sanal bir
  farenin tuşunu basılı tutup parmakları takip eder. Kıstırma ve kenar
  hareketlerini ham dokunuşlardan ölçer, çünkü libinput başparmağı çoğu zaman
  dinlenen parmak sanır. Bunları yerel bir soketle eklentiye iletir. Servis
  durursa touchpad normal çalışmaya devam eder.
- **Bir GNOME Shell eklentisi** GNOME'un hareketlerini üç parmaktan dört
  parmağa taşır, kıstırma ve kenar hareketi animasyonlarını yönetir.
- **Küçük bir kütüphane**, sadece GNOME Shell'e (Wayland oturumu) yüklenip
  touchpad kaydırmasını yeniden ölçekler. libinput her ekranda parmağın
  milimetresi başına sabit bir mesafe kaydırır. Bu yüzden yoğun ekranlarda
  içerik parmağın önüne geçer. GNOME'da bunun için bir ayar yok.

## Sorun giderme

- **Kurulumdan sonra masaüstü açılmıyor**: giriş ekranında adına tıkla, ⚙️
  menüsünden "Ubuntu on Xorg" (ya da "GNOME on Xorg") seçip gir. Kaydırma
  kütüphanesi orada yüklenmez. Sonra `trackpad-like-mac uninstall` çalıştır ve
  [bir issue aç](https://github.com/beylerburak/trackpad-like-mac/issues).
- **Bir hareket çalışmıyor**: `trackpad-like-mac status` çalıştır, servis
  kayıtlarına `journalctl -u trackpad-like-mac` ile bak.

## Sınırlar

- Force Touch ve titreşimli geri bildirim Apple donanımı gerektirir.
- libinput kaydırmaya başlamadan önce birkaç milimetre bekler; bu dışarıdan
  değiştirilemiyor.
- Kaydırma dahili ekrana göre ayarlanır, harici monitörlerde aynı oran kullanılır.
- Sürükleme dışındaki hareketler şimdilik sadece GNOME'da çalışır.

## Lisans

[GPL-3.0-or-later](LICENSE).

Apple ile bir bağlantısı yoktur. Mac, MacBook ve macOS, Apple Inc.'in ticari
markalarıdır.
