# Gizlilik

> [English](PRIVACY.md) | **Türkçe**

Engramkeep tasarım gereği yerel-önceliklidir. Çekirdek paket hesap oluşturmaz,
telemetri toplamaz, bir sunucuya bağlanmaz veya hafızayı dışarıya yüklemez.

## Neler saklanır?

`engramkeep remember` (veya `supersede` / `merge`) çalıştırdığınızda depo şunları
yazar:

- proje kimliği ve başlığı,
- verdiğiniz karar metni (ve geçersiz kılınan karar geçmişi),
- verdiğiniz etiketler,
- oluşturma ve güncelleme zaman damgaları,
- yalnızca üst veri içeren SHA-256 özet zincirli denetim kayıtları (eylem,
  proje, etiketler, zaman damgaları).

Depo, karar metnini `audit.log` içine yazmaz.

`engramkeep fix` çalıştırdığınızda depo, hata metni, doğrulanan çözüm ve isteğe
bağlı proje/çalışma alanı etiketiyle arıza giderme kayıt defterini
(`TROUBLESHOOTING.md`) yazar. Kayıtlar kartlarla aynı redaksiyondan (kullanıcı
dizini adı maskeleme dahil) geçer, atomik olarak yazılır ve ajanlar tarafından
güvenilmez veri olarak işlenir.

## Nerede saklanır?

| Platform | Varsayılan global konum |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` veya `~/.local/share/engramkeep` |

`--home`, `--local` (depo içi `.engramkeep/`) veya `ENGRAMKEEP_HOME` ile
değiştirilebilir. Etkin konumu görmek için `engramkeep path` çalıştırın.

### Proje içi `.engramkeep/` ve `backups/`

- Bir depo içindeki isteğe bağlı `.engramkeep/` klasörü proje kapsamlı kararları
  ve çözümleri tutar; ekip arkadaşlarıyla paylaşılabilir veya yerel bırakılabilir.
  Herhangi bir depoya commit etmeden önce içeriğini dikkatle inceleyin.
- Kurucu yedekleri (`<home>/backups/installer/`), şema göçü yedekleri
  (`<home>/backups/migrations/`) ve şifreleme yedekleri (`<home>/backups/crypto/`),
  diskte değiştirilen dosyaların geri döndürülebilir olması için zaman damgalı
  kopyalarını saklar. Geri alma ihtiyacınız kalmadığında eski yedek klasörlerini
  silin.

## Redaksiyon

Engramkeep, kullanıcı metnini saklamadan önce yaygın sır biçimlerini
`[REDACTED]`, e-posta adreslerini `[REDACTED_EMAIL]` ve ev dizini yollarındaki
kişisel kullanıcı adlarını (`C:\Users\<ad>`, `/Users/<ad>`, `/home/<ad>`)
`[REDACTED_USER]` ile değiştirir.

Yerleşik desenler OpenAI/Anthropic/Supabase/Groq/xAI/Perplexity/Resend/Linear/
Databricks anahtarlarını, GitHub belirteçlerini, Google API anahtarlarını, AWS
erişim anahtarlarını, Slack belirteçlerini, JWT'leri, özel anahtar bloklarını,
Bearer belirteçlerini ve kimlik bilgisi benzeri `anahtar=değer` atamalarını kapsar.

`<home>/redact.json` içinde kuruma özgü ek desenler tanımlayabilirsiniz (her
kural derlenmeden önce ReDoS riski taşıyan iç içe niceleyicilere ve boş eşleşmeye
karşı doğrulanır). `engramkeep doctor` hem yerleşik hem özel kurallarla kartları
ve `TROUBLESHOOTING.md` dosyasını tarar.

Redaksiyon **en iyi çaba (best-effort)** yaklaşımıyla çalışır. Şunları güvenilir
biçimde yakalayamaz:

- kodlanmış, bölünmüş veya şifrelenmiş sırlar,
- görseller, arşivler veya ikili dosyalardaki sırlar,
- yerleşik veya `redact.json` kurallarında bulunmayan yeni belirteç biçimleri,
- saklama öncesinde dönüştürülen proje adları veya etiketlerdeki sırlar,
- e-posta ve standart ev dizini yolları dışındaki serbest kişisel veriler.

Engramkeep'i bir parola/sır yöneticisi olarak kullanmayın. Bir kimlik bilgisi
yanlışlıkla kaydedildiyse anahtarı yenileyin (rotate) ve kartı kaldırın.

## İsteğe bağlı disk şifrelemesi

Tam disk şifrelemesinin ötesinde şifreli dosyalar gerekiyorsa isteğe bağlı
`pip install 'engramkeep[crypto]'` eklentisini kurup `engramkeep encrypt` /
`engramkeep decrypt` komutlarını kullanabilirsiniz. Parolalar yalnızca
`ENGRAMKEEP_PASSPHRASE` ortam değişkeninden veya etkileşimli terminal isteminden
(`getpass`) okunur; kabuk geçmişine veya süreç listesine sızmaması için asla CLI
argümanı olarak alınmaz.

**Kapsam ve sınırlamalar:**

- Şifreleme yalnızca `projects/*.md` ve `TROUBLESHOOTING.md` dosyalarını kapsar.
- `INDEX.md`, `RECENT_ACTIVITY.md`, `audit.log` ve `meta.json` düz metin kalır
  (proje kimlikleri, başlıklar, etiketler ve aktivite zaman damgaları bu
  dosyalarda görünür durumdadır).
- `engramkeep encrypt --apply`, şifreleme öncesinde `<home>/backups/crypto/`
  altına düz metin yedek yazar; şifre çözmeyi doğruladıktan sonra eski şifreleme
  yedeklerini silin.
- Şeffaf ve tüm dizini kapsayan gizlilik için işletim sisteminin tam disk
  şifrelemesini (BitLocker, FileVault, LUKS) tercih edin.

## Transkript keşfi ve içe aktarma

- `engramkeep import --discover`, standart yerel ajan oturum klasörlerinde
  yalnızca dosya üst verilerini (yol, boyut, değişiklik zamanı, algılanan biçim)
  inceler ve sembolik bağlantıları atlar; transkript içeriğini otomatik okumaz
  veya değiştirmez.
- `engramkeep import --file <yol>` varsayılan olarak kuru çalıştırma yapar;
  `--apply` veya `--interactive` ile onay verilmedikçe depoya yazmaz.

## Yerel Git eşitleme

`engramkeep sync` isteğe bağlıdır ve yalnızca yerelde çalışır:

- Yalnızca izin listesindeki dosyaları (`projects/*.md`, `INDEX.md`,
  `TROUBLESHOOTING.md`) ve izlenen silinmiş kartları sahneler (`stage`).
- `trash/`, `audit.log`, `backups/` veya keyfi dosyaları asla sahnelemez; asla
  `git add -A` veya `git push` çalıştırmaz.
- Her `--commit` öncesinde sır taraması çalıştırır ve sır bulunursa işlemi
  iptal eder.

## MCP

MCP sunucusu istemci süreciyle `stdio` üzerinden haberleşir. Ağ soketi açmaz ve
hafızayı dışarıya göndermez. Araç çıktıları ve kaynaklar yalnızca bağlı istemciye
gider. Varsayılan olarak salt okunur araçlar açıktır; yazma araçları için
`--allow-write` gerekir.

## Panel (Dashboard)

Panel, `127.0.0.1` adresine bağlı yerel bir HTTP sunucusudur ve internete
bağlanmaz. Oturuma özel belirteç URL parçasında (fragment) iletilir, tarayıcının
`sessionStorage` alanında tutulur ve yalnızca loopback sunucusuna
`X-Engramkeep-Token` başlığıyla gönderilir. Panel çerez bırakmaz, CORS başlığı
göndermez ve günlükte yalnızca HTTP yöntemi ile yolu tutar (sorgu dizeleri veya
başlıklar kaydedilmez).

Panel varsayılan olarak salt okunurdur. Yazma işlemleri yalnızca `--allow-write`
ve açık onay (`confirm: true`) ile etkinleşir.

## Engramkeep ne yapmaz?

- Telemetri, analitik, çökme raporu veya güncelleme kontrolü yok.
- Bulut eşitleme, otomatik Git push veya uzak yedekleme yok.
- Arka planda otomatik transkript tarama yok.
- Arka plan servisi (daemon) veya otomatik başlatma kaydı yok.
- Zorunlu üçüncü taraf çalışma zamanı bağımlılığı yok.

## Paylaşım ve yedekler

Hafıza dizinini kopyalar veya yedeklerseniz içeriğinden siz sorumlusunuz. Hem
`trash/` hem de `backups/`, unutmak istediğiniz kartları veya eski dosya
sürümlerini barındırabilir. Dizini paylaşmadan önce inceleyin ve kişisel hafıza
dizininizi herkese açık bir depoya commit etmeyin.

Depodaki `.gitignore` yaygın çalışma zamanı dosyalarını, arşivleri, günlükleri
ve sır dosyası uzantılarını dışlar; ancak commit ettiğiniz dosyaları gözden
geçirmenin yerini tutmaz.

## Veri silme

- `engramkeep forget <proje> --yes` kartı `trash/` dizinine taşır
  (`engramkeep restore <proje>` ile geri alınabilir).
- `engramkeep trash --purge --yes`, `trash/` içindeki tüm kartları kalıcı olarak
  siler.
- Her şeyi kaldırmak için hafıza dizinini (ve oluşturulduysa depo içi
  `.engramkeep/` dizinini) silin.

Silinmesi gereken herhangi bir uzak kopya yoktur.

## Çocuklar ve düzenlemeye tabi veriler

Engramkeep bir geliştirici aracıdır, resmi kayıt sistemi değildir. Düzenlemeye
tabi kişisel veriler, sağlık verileri, finansal veriler veya çocuklara ait
bilgiler için kullanmayın.

## İletişim

Gizlilik soruları kişisel veri içermeyen bir GitHub issue olarak açılabilir.
Güvenlik açıkları için [SECURITY.md](../SECURITY.md) sürecini izleyin.
