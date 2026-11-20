# Uyumluluk

> [English](COMPATIBILITY.md) | **Türkçe**

Engramkeep 1.2.1 dosya biçimi düzeyinde taşınabilirdir. Kurucu (`install`),
desteklenen ajan yapılandırmalarına yönetilen bloklar, MCP kayıtları ve
beceri (`SKILL.md`) dosyaları yazar; dokunduğu her dosyayı zaman damgalı
bir bildirim (`manifest.json`) ile yedekler. Şablonların elle kopyalanması
da desteklenir.

## Çalışma ortamı

| Öğe | Destek |
| --- | --- |
| Python | 3.10, 3.11, 3.12, 3.13, 3.14 |
| Windows | Desteklenir |
| macOS | Desteklenir |
| Linux | Desteklenir |
| Zorunlu çalışma zamanı bağımlılığı | Yok (yalnızca Python standart kütüphanesi) |
| İsteğe bağlı eklentiler | `engramkeep[crypto]` (`encrypt`/`decrypt` için `cryptography>=43.0`) |
| Dosya kodlaması | UTF-8 |
| Üretilen satır sonları | LF |

CI testleri Windows, Linux ve macOS üzerinde Python 3.10–3.14 sürümlerinde çalışır.

## Ajanlar

| Ajan | Kurucu kimliği | Taşınabilir dosya | Tipik hedef | MCP (`--mcp`) | Beceri (`--skill`) |
| --- | --- | --- | --- | --- | --- |
| OpenCode | `opencode` | `AGENTS.md`, `SKILL.md` | `~/.config/opencode/AGENTS.md` | `opencode.json` | Evet |
| Claude Code | `claude-code` | `CLAUDE.md`, `SKILL.md` | `~/.claude/CLAUDE.md` | `~/.claude.json` / `.mcp.json` | Evet |
| OpenAI Codex | `codex` | `AGENTS.md` | `~/.codex/AGENTS.md` | `~/.codex/config.toml` / `.codex/config.toml` (TOML) | Evet |
| Cursor | `cursor` | `.mdc` kuralı | `.cursor/rules/engramkeep.mdc` | `.cursor/mcp.json` | Evet |
| Windsurf | `windsurf` | Markdown kuralı | `.windsurf/rules/engramkeep.md` | `~/.codeium/windsurf/mcp_config.json` / `.windsurf/mcp.json` | Evet |
| Gemini CLI | `gemini-cli` | `GEMINI.md` | `~/.gemini/GEMINI.md` | `~/.gemini/settings.json` / `.gemini/settings.json` | Evet |
| Antigravity | `antigravity` | `GEMINI.md`, `AGENTS.md` | `~/.gemini/GEMINI.md` | `~/.gemini/antigravity/mcp_config.json` / `.gemini/mcp.json` | Evet |
| GitHub Copilot | `copilot` | depo yönergeleri | `.github/copilot-instructions.md` | Atlanır (standart değil) | Evet |
| Cline | `cline` | `.clinerules` | proje kökü | `.cline/mcp_settings.json` | Evet |
| Roo Code | `roo` | `.roorules` | proje kökü | `.roo/mcp.json` | Evet |
| Herhangi bir MCP istemcisi | yok | MCP stdio | `engramkeep mcp` | Doğal | yok |

Bu yollar varsayımdır, garanti değildir; ajan üreticileri bunları değiştirebilir.
`engramkeep install --list` güncel varsayımları yazdırır ve varsayılan kuru
çalıştırma (`--dry-run`) herhangi bir dosya yazmadan önce tüm hedefleri gösterir.

## Kurucu davranışı

- Varsayılan olarak kuru çalıştırma yapar; `--apply` yazar, `--uninstall`
  yönetilen blokları temizler ve `--restore RUN_ID` değişiklik öncesi
  yedekleri geri yükler (uygulamak için `--apply`).
- Yönetilen Markdown blokları `<!-- engramkeep:begin -->` ve
  `<!-- engramkeep:end -->` ile; OpenAI Codex TOML MCP blokları ise
  `# engramkeep:mcp:begin` ve `# engramkeep:mcp:end` ile sınırlanır. Yeniden
  çalıştırma yalnızca yönetilen bloğu günceller.
- `--agent all` aynı kural dosyasını paylaşan iki ajanla karşılaştığında
  (örneğin `~/.gemini/GEMINI.md` kullanan `gemini-cli` ve `antigravity`),
  kurucu dosyayı bir kez yazar ve ikinci ajanı `shared` olarak kaydeder.
- Mevcut dosyalar zaman damgasıyla yedeklenir ve `<home>/backups/installer/`
  altındaki `manifest.json` dosyasına işlenir.
- `--scope auto`, ajanın belgelenmiş bir global hedefi varsa globali, yoksa
  proje hedefini seçer. `--scope project --project-dir PATH` proje kapsamını
  zorlar.
- `--mcp`, 9 ajanda MCP sunucusunu kaydeder (varsayılan olarak salt okunur;
  isteğe bağlı yazma için `--mcp-allow-write`). `engramkeep` global `PATH`
  üzerindeyse (geçici sanal ortam dışındaysa) taşınabilir komut tercih edilir;
  açıkça geçersiz kılmak için `--mcp-command` kullanılabilir.
- `--skill`, paketteki `SKILL.md` dosyasını ajanın beceri dizinine kurar.
- Güvenli biçimde ayrıştırılamayan dosyalar asla düzenlenmez.

## Katmanlı hafıza

Mevcut depoda (veya depo köküne kadar üst dizinlerden birinde) başlatılmış
bir `.engramkeep/` deposu varsa okuma komutları (`search`, `show`, `list`,
`fixes`, `context`, `mcp`, `dashboard`) bunu otomatik olarak global deponun
üzerine katmanlar. Aynı kimliğe sahip proje kartları global kartları ezer.
Yazma ve bakım komutlarında doğrudan `.engramkeep/` hedeflemek için `--local`,
`mcp` ve `dashboard` komutlarında katmanı kapatmak veya özelleştirmek için
`--no-local` / `--project-store DIR` kullanılabilir.

## "Taşınabilir" ne anlama gelir?

- Aynı Markdown kartları kabuk çalıştırabilen her ajan tarafından okunabilir.
- Aynı `AGENTS.md` ve `SKILL.md` metinleri farklı araçlara kopyalanabilir.
- Ajana özgü bir veritabanı veya ikili biçim kullanılmaz.
- Engramkeep her ajanla yerel entegrasyon iddiasında bulunmaz.

## MCP

MCP stdio sunucusu şunları destekler:

- stdio aktarımı,
- satır sonuyla ayrılmış JSON-RPC 2.0 çerçevelemesi,
- `2024-11-05`, `2025-03-26`, `2025-06-18` ve `2025-11-25` arasında protokol
  sürüm müzakeresi,
- varsayılan olarak salt okunur araçlar,
- katmanlı proje + global çözümleme (`--project-store DIR` / `--no-local`).

Salt okunur araçlar: `engramkeep_context`, `engramkeep_search`,
`engramkeep_show`, `engramkeep_list`, `engramkeep_recent`, `engramkeep_doctor`
ve `engramkeep_fixes`. Yazma araçları (`engramkeep_remember`,
`engramkeep_record_fix`, `engramkeep_supersede`) yalnızca sunucu
`--allow-write` ile başlatıldığında açılır. MCP üzerinden kart silme (`forget`)
aracı yoktur.

MCP kaynakları `engramkeep://projects/<id>`, `engramkeep://index`,
`engramkeep://troubleshooting` ve `engramkeep://recent` adreslerini; MCP
istemleri ise `session-start`, `post-mortem-fix` ve `decision-review`
şablonlarını sunar.

Sunucu eski `Content-Length` çerçevelemesini kullanmaz ve TCP dinleyicisi
açmaz. Başlatmak için `engramkeep mcp`, durumunu görmek için
`engramkeep mcp --status [--json]` çalıştırın.

## Panel (Dashboard)

Yerel panel şunları kullanır:

- yalnızca `127.0.0.1` loopback bağlantısı,
- URL parçasında (fragment) iletilip `X-Engramkeep-Token` başlığıyla gönderilen
  oturuma özel belirteç,
- katı Content-Security-Policy ve yalnızca metin (`textContent`) kart gösterimi,
- katmanlı depo farkındalığı (etkin depo yolu ve proje/global rozetleri),
- Doctor sağlık kontrolü, SHA-256 denetim zinciri doğrulaması ve çöp kutusu
  (`trash`) görünümü,
- varsayılan olarak salt okunur API.

`engramkeep dashboard` (tarayıcıyı açmak için `--open`) ile başlatılır.
Hatırlama, çözüm ekleme, karar güncelleme (`supersede`) ve çöp kutusundan geri
yükleme işlemleri `--allow-write` gerektirir; tüm yazmalar yalnızca `POST` ve
`confirm: true` ile kabul edilir. Panel çerez bırakmaz, CORS başlığı açmaz ve
silme (`forget`) düğmesi içermez.

## Eşitleme, denetim ve isteğe bağlı şifreleme

- **Denetim günlüğü (`audit.log`):** `engramkeep doctor` tarafından doğrulanan,
  sıfır bağımlılıklı SHA-256 özet zinciri kullanır.
- **Git eşitleme (`sync`):** Zorunlu commit öncesi sır taramasıyla yalnızca
  izin listesindeki dosyaları (`projects/*.md`, `INDEX.md`, `TROUBLESHOOTING.md`)
  ve izlenen silinmiş kartları yerel Git commit'ine hazırlar; asla `git add -A`
  veya `git push` çalıştırmaz.
- **İsteğe bağlı şifreleme:** `engramkeep[crypto]` kuruluysa `engramkeep encrypt`
  / `engramkeep decrypt` komutları `projects/*.md` ve `TROUBLESHOOTING.md`
  dosyaları için AES-256-GCM + Scrypt şifrelemesi sunar. Normal arama/okuma
  öncesinde şifre çözülmelidir.

## Bilinen sınırlamalar

- Proje kimlikleri ASCII slug biçimindedir; ASCII dışı adlar dönüştürülür veya
  reddedilir.
- Yazma işlemleri iş parçacıkları ve süreçler arasında sınırlı zaman aşımıyla
  danışma kilidi (`.engramkeep.lock`) üzerinden sıraya konur.
- Arama sözcükseldir (BM25 + tırnaklı ifade + EN/TR kavram genişletme + Türkçe
  ön ek eşleştirme); anlamsal veya vektör araması değildir.
- İsteğe bağlı disk şifrelemesi yalnızca `projects/*.md` ve `TROUBLESHOOTING.md`
  dosyalarını bütün olarak şifreler (şifreli arama indeksi yoktur; `INDEX.md`,
  `RECENT_ACTIVITY.md`, `audit.log` ve `meta.json` düz metin kalır). Şeffaf ve
  tüm diski kapsayan gizlilik için tam disk şifrelemesi tercih edilmelidir.
- Bozuk biçimli kartlar arama/listelemede atlanır ve `doctor` tarafından
  raporlanır.
