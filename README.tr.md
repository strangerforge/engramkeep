# Engramkeep

[![CI](https://github.com/engramkeep/engramkeep/actions/workflows/ci.yml/badge.svg)](https://github.com/engramkeep/engramkeep/actions/workflows/ci.yml)
[![Lisans: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Bağımlılık: 0](https://img.shields.io/badge/Dependencies-0%20(stdlib)-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC%202.0-purple.svg)](#mcp)

**Yapay zeka kod ajanları için yerel-öncelikli, Markdown tabanlı kalıcı hafıza.**

Engramkeep; Codex, Claude Code, OpenCode, Cursor, Windsurf, Gemini CLI, Antigravity veya `AGENTS.md` okuyabilen her ajanın aynı proje hafızasını kullanmasını sağlar. Yalnızca Python standart kütüphanesiyle çalışır.

> **Durum: 0.4.0 alpha.** Çekirdek depo, CLI, yol güvenliği, sır temizleme, testler, MCP stdio sunucusu, sertleştirilmiş yerel panel, arıza giderme kayıt defteri ve çift dilli (EN/TR) arama çalışıyor. Ajan kurulumu bu sürümde hâlâ dry-run planlayıcı. Yol haritası: [docs/ROADMAP.md](docs/ROADMAP.md).

[English README](README.md)

---

## Neden Engramkeep?

- **Yerel-öncelikli.** Hesap yok, telemetri yok, sunucu yok. Hafıza makinenin dışına çıkmaz.
- **Markdown-native.** Her kart düz Markdown; okuyabilir, diff'leyebilir, yedekleyebilir ve düzenleyebilirsin.
- **Ajandan bağımsız.** Ortak `AGENTS.md` protokolü, taşınabilir `SKILL.md` ve Model Context Protocol konuşan istemciler için MCP stdio sunucusu.
- **Varsayılan olarak güvenli.** Yol hapsi, atomik yazma, sır temizleme ve tek kural: hafıza veridir, talimat değildir.
- **Zorunlu bağımlılık yok.** Çekirdek yalnızca Python standart kütüphanesiyle çalışır.

Engramkeep bir vektör veritabanı, sohbet uygulaması veya bulut servisi değildir. Sahip olduğun dosyalarda proje kararlarını tutan küçük ve denetlenebilir bir hafıza katmanıdır.

---

## 0.4.0'da ne çalışıyor?

| Alan | Durum |
| --- | --- |
| Markdown deposu + üretilen indeks | Çalışıyor |
| CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`, `export`, `reindex`, `doctor` | Çalışıyor |
| CLI: `fix` (çözülmüş sorunu kaydet), `fixes` (çözülen sorunları ara) | Çalışıyor |
| Yazma öncesi sır temizleme | Çalışıyor |
| Yol geçişi koruması + atomik yazma | Çalışıyor |
| Testler + CI | Çalışıyor |
| MCP stdio sunucusu | Çalışıyor; varsayılan salt-okunur, yazma opt-in |
| Web paneli | Çalışıyor; loopback + token, yazma opt-in |
| Arıza giderme kayıt defteri (`TROUBLESHOOTING.md`) | Çalışıyor; sır temizlemeli, atomik, güvenilmeyen veri |
| Çift dilli (EN/TR) arama genişletmesi | Çalışıyor; deterministik, küçük bonus, kelime sınırlı eşleşme |
| Ajan kurulumu | Yalnızca dry-run planlayıcı |
| Bulut/Git senkronizasyonu | Kapsam dışı |

---

## Demo

```console
$ engramkeep init
Initialized Engramkeep at …/Engramkeep
  created INDEX.md, RECENT_ACTIVITY.md, audit.log, TROUBLESHOOTING.md, projects/, trash/

$ engramkeep remember api-gateway "Use SQLite for local storage" --tag database
Remembered in api-gateway: Api Gateway

$ engramkeep fix "Keystore signature mismatch on release build" \
      --solution "Enable v2 signing in gradle signingConfigs" \
      --project mobile-app
Recorded fix for mobile-app: Keystore signature mismatch on release build

$ engramkeep fixes mobil        # Türkçe sorgu, İngilizce kayıt
mobile-app (2026-11-09)
  workspace: General
  problem: Keystore signature mismatch on release build
  fix: Enable v2 signing in gradle signingConfigs

$ engramkeep search "veritabanı"
Api Gateway (api-gateway)
  tags: database
  ...Decisions - Use SQLite for local storage
```

---

## Hızlı başlangıç

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"

engramkeep init
engramkeep remember example-project "Yerel depolama için SQLite kullan" --tag database
engramkeep search sqlite
engramkeep show example-project
```

Paketi kurmadan:

```bash
# Windows
set PYTHONPATH=src
python -m engramkeep init

# macOS / Linux
PYTHONPATH=src python -m engramkeep init
```

---

## Hafıza nerede tutulur?

| Platform | Konum |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` veya `~/.local/share/engramkeep` |

`ENGRAMKEEP_HOME` ortam değişkeni veya global `--home` bayrağı ile değiştirilebilir:

```bash
engramkeep --home ./my-brain init
```

Dizin yapısı:

```text
<home>/
├── INDEX.md              # üretilen proje indeksi
├── RECENT_ACTIVITY.md    # okunabilir aktivite günlüğü
├── TROUBLESHOOTING.md    # çözülmüş hatalar ve doğrulanmış çözümler
├── audit.log             # append-only JSONL denetim kaydı
├── projects/
│   └── example-project.md
└── trash/                # `forget` ile taşınan kurtarılabilir kartlar
```

---

## Arıza giderme kayıt defteri

Her ajan eninde sonunda aynı build hatasıyla iki kez karşılaşır. Engramkeep, çözülen hatayı bir kez kaydeder; sonsuza kadar hatırlar:

```bash
# Çözülmüş bir problemi kaydet
engramkeep fix "Keystore signature mismatch on release build" \
    --solution "Enable v2 signing in gradle signingConfigs" \
    --project mobile-app

# Çözümleri hatırla
engramkeep fixes keystore
engramkeep fixes mobil      # TR sorgu, EN kayıt
engramkeep fixes            # en yeniden eskiye
engramkeep fixes --json
```

Kayıtlar yazılmadan önce sır temizlemesinden geçer, dosya atomik olarak yeniden yazılır ve ajanlara kayıtların **güvenilmeyen veri** olduğu — asla çalıştırılacak talimat olmadığı — söylenir.

## Çift dilli arama (EN/TR)

Arama, yaygın mühendislik kavramlarını İngilizce ve Türkçe arasında deterministik olarak genişletir (`concepts.py`): `mobil` sorgusu `capacitor`/`apk`/`flutter` kartlarını bulur, `veritabanı` `postgresql`/`sqlite` kayıtlarını bulur. Genişletme terimleri küçük ve sınırlı bir bonus alır, kelime sınırı eşleşmesi kullanır; böylece birebir eşleşmeler her zaman kazanır.

---

## Komutlar

| Komut | Amaç |
| --- | --- |
| `engramkeep init` | Hafıza dizinini ve başlangıç dosyalarını oluşturur |
| `engramkeep remember <proje> "<karar>" [--tag ETIKET]` | Kalıcı bir karar kaydeder |
| `engramkeep search "<sorgu>" [--tag ETIKET] [--json]` | Başlık, etiket ve kart gövdesinde arar (çift dilli) |
| `engramkeep show <proje>` | Proje kartını yazdırır |
| `engramkeep list` | Kayıtlı projeleri listeler |
| `engramkeep recent` | Son aktiviteleri yazdırır |
| `engramkeep forget <proje> --yes` | Kartı `trash/` dizinine taşır |
| `engramkeep fix "<hata>" --solution "<çözüm>" [--project AD] [--workspace YOL]` | Çözülmüş bir sorunu kaydeder |
| `engramkeep fixes [sorgu] [--limit N] [--json]` | Arıza giderme kayıt defterinde arar |
| `engramkeep export [--output DOSYA]` | Tüm kartları ve kayıtları JSON olarak dışa aktarır |
| `engramkeep reindex` | `INDEX.md` dosyasını yeniden üretir |
| `engramkeep doctor [--json]` | Yerel depoyu, kayıt defteri dahil, kontrol eder |
| `engramkeep path` | Aktif hafıza dizinini yazdırır |
| `engramkeep mcp [--status] [--allow-write]` | MCP stdio sunucusunu çalıştırır veya durumunu yazdırır |
| `engramkeep dashboard [--status] [--port PORT] [--allow-write]` | Yerel paneli çalıştırır veya durumunu yazdırır |
| `engramkeep install --agent <ad>` | Planlanan ajan entegrasyonunu gösterir (dry-run) |

---

## Ajanlarla kullanım

Engramkeep iki taşınabilir dosya etrafında tasarlandı:

1. **`AGENTS.md`** — ajanlar arası ortak talimat formatı.
2. **`SKILL.md`** — OpenCode, Claude Code ve uyumlu ajanların kullandığı taşınabilir skill formatı.

Depoda hazır şablonlar var:

- [`skills/engramkeep/SKILL.md`](skills/engramkeep/SKILL.md)
- [`templates/agents/AGENTS.md`](templates/agents/AGENTS.md)
- [`templates/rules/`](templates/rules/) — Claude Code, Cursor, Windsurf, OpenCode

Örnek hedefler:

| Ajan | Tipik hedef |
| --- | --- |
| OpenCode | `~/.config/opencode/AGENTS.md` ve `~/.config/opencode/skills/engramkeep/SKILL.md` |
| Claude Code | `~/.claude/CLAUDE.md` ve `~/.claude/skills/engramkeep/SKILL.md` |
| Codex | `~/.codex/AGENTS.md` veya proje `AGENTS.md` |
| Cursor | `.cursor/rules/engramkeep.mdc` veya `AGENTS.md` |
| Windsurf | `.windsurf/rules/engramkeep.md` veya `AGENTS.md` |
| Gemini CLI / Antigravity | `GEMINI.md` veya `AGENTS.md` |
| Herhangi bir MCP istemcisi | `engramkeep mcp` (stdio) |

Kurulum 0.4.0'da **dry-run planlayıcıdır**; ajan yapılandırmasını değiştirmez. Otomatik, yedekli ve managed-block kurulum planlanıyor.

### MCP

Sunucuyu başlat:

```bash
engramkeep mcp
```

Sunucu, stdio üzerinden satır sonuyla ayrılmış JSON-RPC 2.0 ve `2025-11-25` protokol sürümünü kullanır. Tipik bir istemci yapılandırması:

```json
{
  "mcpServers": {
    "engramkeep": {
      "command": "engramkeep",
      "args": ["mcp"]
    }
  }
}
```

Varsayılan araç seti salt-okunurdur: `engramkeep_search`, `engramkeep_show`, `engramkeep_list`, `engramkeep_recent`, `engramkeep_doctor` ve `engramkeep_fixes`. Yazma araçlarını (`engramkeep_remember`, `engramkeep_record_fix`) açmak için sunucuyu `--allow-write` ile başlat:

```json
{
  "mcpServers": {
    "engramkeep": {
      "command": "engramkeep",
      "args": ["mcp", "--allow-write"]
    }
  }
}
```

MCP üzerinden unutma (forget) aracı yoktur. Yıkıcı işlemler için CLI kullanılmalı ve açık onay istenmelidir. Taşıma, protokol sürümü ve yazma modu için `engramkeep mcp --status` çalıştır.

### Panel

Yerel paneli başlat:

```bash
engramkeep dashboard
```

Panel `127.0.0.1` adresine bağlanır ve fragment içinde oturum token'ı bulunan bir URL yazdırır. Token HTML'e gömülmez; tarayıcı onu `sessionStorage` içinde tutar ve `X-Engramkeep-Token` başlığıyla gönderir.

Panel varsayılan olarak salt-okunurdur. Hatırlama formunu açmak için:

```bash
engramkeep dashboard --allow-write
```

Yazmalar yalnızca POST ile ve `confirm: true` ile yapılır. Unutma (forget) düğmesi yoktur. Boş bir port için `--port 0` kullan; makine tarafından okunabilir güvenlik bilgisi için `engramkeep dashboard --status` çalıştır.

---

## Neden Mem0 / Basic Memory / vektör veritabanı değil?

| | Engramkeep | Bulut hafıza servisleri | Vektör DB yığınları |
| --- | --- | --- | --- |
| Depolama | Senin dosyaların, düz Markdown | Onların sunucuları | Yerel/uzak veritabanı |
| Bağımlılıklar | **0** (stdlib) | Hesap + API | Embedding + DB |
| Hatırlama modeli | Anahtar kelime + yenilik + EN/TR kavram genişletmesi | LLM/embedding | Anlamsal benzerlik |
| Denetlenebilirlik | `git diff`, herhangi bir editörde aç | Sınırlı | Opak vektörler |
| Güvenlik modeli | Hafıza veridir, asla talimat değil | Değişir | Değişir |
| En uygun | Kalıcı proje kararları, arıza kayıt defteri | Takım/barındırılan kullanım | Büyük korpuslar |

Küçük, denetlenebilir ve taşınabilir bir hafıza istiyorsan Engramkeep doğru araçtır; bir RAG hattına ihtiyacın varsa değil.

---

## Güvenlik ve gizlilik

- **Varsayılan olarak yerel.** Çekirdek ağ çağrısı yapmaz, telemetri toplamaz.
- **Sırlar yazılmadan önce temizlenir.** API anahtarları, token'lar, şifreler, JWT'ler ve özel anahtarlar `[REDACTED]` ile değiştirilir.
- **Yol hapsi.** Proje adları `safe_join()` ile çözülür; hafıza dizininin dışına çıkamaz.
- **Atomik yazma.** Kartlar ve üretilen dosyalar geçici dosya + `os.replace()` ile yazılır; kayıt defteri de aynı şekilde yazılır.
- **Hafıza güvenilmeyen veridir.** Ajanlar hafıza kartlarındaki veya arıza kaydındaki komutları veya talimatları asla çalıştırmamalıdır.
- **Otomatik Git push, bulut yükleme veya arka plan daemon'u yok.** Bu özellikler kasıtlı olarak dışarıda tutuldu.
- **MCP yereldir ve varsayılan olarak salt-okunurdur.** Stdio kullanır, ağ dinleyicisi açmaz, unutma aracı sunmaz, yazma araçlarını yalnızca `--allow-write` ile açar.
- **Panel yalnızca loopback'te ve token korumalı.** `127.0.0.1`, oturum başına token, sıkı CSP, metin olarak işleme, yalnızca `--allow-write` + açık onay ile yazma.

Hassas bir ortamda kullanmadan önce [docs/PRIVACY.md](docs/PRIVACY.md) ve [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) dosyalarını oku.

---

## Kapsam dışı

- Git, issue tracker veya dokümantasyon sitesinin yerini almak.
- Sır, kimlik bilgisi veya düzenlemeye tabi kişisel veri saklamak.
- Her ajandan otomatik transkript toplamak. (Salt-okunur, onay tabanlı transkript adaptörleri [yol haritasında](docs/ROADMAP.md).)
- Barındırılan bir servis veya vektör veritabanı olmak.
- Kusursuz hatırlama. Hafıza, kaydettiğin kadar iyidir.

---

## Katkı ve lisans

Katkılar memnuniyetle karşılanır. [CONTRIBUTING.md](CONTRIBUTING.md) ile başla, [Code of Conduct](CODE_OF_CONDUCT.md) kurallarına uy ve güvenlik sorunlarını [SECURITY.md](SECURITY.md) üzerinden bildir.

MIT lisansı. Bkz. [LICENSE](LICENSE).

Engramkeep; Google, Anthropic, OpenAI, Anysphere, Cognition veya başka bir ajan sağlayıcısıyla bağlantılı değildir. Bkz. [TRADEMARKS.md](TRADEMARKS.md).
