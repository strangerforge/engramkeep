# Engramkeep

[![CI](https://github.com/strangervibe/engramkeep/actions/workflows/ci.yml/badge.svg)](https://github.com/strangervibe/engramkeep/actions/workflows/ci.yml)
[![Kapsam: 85%](https://img.shields.io/badge/Coverage-85%25-brightgreen.svg)](docs/BENCHMARK.md)
[![Lisans: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Bağımlılık: 0](https://img.shields.io/badge/Dependencies-0%20(stdlib)-brightgreen.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC%202.0-purple.svg)](#mcp)

**Yapay zeka kod ajanları için yerel-öncelikli, Markdown tabanlı kalıcı hafıza.**

Engramkeep; Codex, Claude Code, OpenCode, Cursor, Windsurf, Gemini CLI,
Antigravity veya `AGENTS.md` okuyabilen her ajanın aynı proje hafızasını
kullanmasını sağlar. Yalnızca Python standart kütüphanesiyle çalışır.

> **Durum: 0.5.0 alpha.** Depo, CLI, MCP sunucusu, panel, arıza giderme kayıt
> defteri, çift dilli arama ve yedekli ajan kurulumu çalışıyor. Bulut
> senkronizasyonu, transkript adaptörleri ve şema geçişleri hâlâ yol
> haritasında. Bkz. [docs/ROADMAP.md](docs/ROADMAP.md).

[English README](README.md)

---

![Engramkeep paneli](https://raw.githubusercontent.com/strangervibe/engramkeep/main/assets/dashboard.png)

<p align="center">
  <img src="https://raw.githubusercontent.com/strangervibe/engramkeep/main/assets/demo.gif" alt="Engramkeep demosu: projeler, arama, kartlar, aktivite ve doctor" width="720">
</p>

---

## Neden Engramkeep?

- **Yerel-öncelikli.** Hesap yok, telemetri yok, sunucu yok. Hafıza makinenin dışına çıkmaz.
- **Markdown-native.** Her kart düz Markdown; okuyabilir, diff'leyebilir, yedekleyebilir ve düzenleyebilirsin.
- **Ajandan bağımsız.** Ortak `AGENTS.md` protokolü, taşınabilir `SKILL.md` ve Model Context Protocol konuşan istemciler için MCP stdio sunucusu.
- **Tek komutla kurulum.** `engramkeep install --apply` hafıza protokolünü on ajana bağlar; managed block, zaman damgalı yedek ve temiz kaldırma ile.
- **Varsayılan olarak güvenli.** Yol hapsi, atomik yazma, sır temizleme ve tek kural: hafıza veridir, talimat değildir.
- **Zorunlu bağımlılık yok.** Çekirdek yalnızca Python standart kütüphanesiyle çalışır.

Engramkeep bir vektör veritabanı, sohbet uygulaması veya bulut servisi
değildir. Sahip olduğun dosyalarda proje kararlarını tutan küçük ve
denetlenebilir bir hafıza katmanıdır.

---

## 0.5.0'da ne çalışıyor?

| Alan | Durum |
| --- | --- |
| Markdown deposu + üretilen indeks | Çalışıyor |
| CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`, `export`, `reindex`, `doctor` | Çalışıyor |
| CLI: `fix` (çözülmüş sorunu kaydet), `fixes` (çözülen sorunları ara) | Çalışıyor |
| Yazma öncesi sır temizleme | Çalışıyor |
| Yol geçişi koruması + atomik yazma | Çalışıyor |
| Linux, macOS ve Windows'ta testler + CI | 203 başarılı test, %85 kapsam |
| MCP stdio sunucusu | Çalışıyor; varsayılan salt-okunur, yazma opt-in |
| Web paneli | Çalışıyor; loopback + token, yazma opt-in |
| Arıza giderme kayıt defteri (`TROUBLESHOOTING.md`) | Çalışıyor; sır temizlemeli, atomik, güvenilmeyen veri |
| Çift dilli (EN/TR) arama genişletmesi | Çalışıyor; deterministik, kelime sınırlı eşleşme |
| Ajan kurulumu | Çalışıyor; managed block, yedek, kaldırma |
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

Tamamen sentetik bir depo [`examples/demo-brain/`](examples/demo-brain)
dizininde duruyor. Depodaki JSON kaynaklarından
`python scripts/build_demo_brain.py` ile üretilir; gerçek proje verisi içermez.

---

## Hızlı başlangıç

```bash
pipx install engramkeep     # veya: pip install engramkeep
engramkeep init
engramkeep remember example-project "Yerel depolama için SQLite kullan" --tag database
engramkeep search sqlite
engramkeep show example-project
```

Kaynak koddan:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
engramkeep init
```

Paketi kurmadan:

```bash
# Windows
set PYTHONPATH=src
python -m engramkeep init

# macOS / Linux
PYTHONPATH=src python -m engramkeep init
```

Kendi hafızana dokunmadan demo deposunu dene:

```bash
engramkeep --home examples/demo-brain search "docker arm64"
engramkeep --home examples/demo-brain fixes "database is locked"
engramkeep --home examples/demo-brain dashboard
```

---

## Hafıza protokolünü ajanlarına kur

Kurulum, ajan talimat dosyalarına küçük bir managed block yazar. Varsayılan
olarak **dry run**'dır: `--apply` vermeden hiçbir şey değişmez.

```bash
engramkeep install --list                 # desteklenen ajanlar
engramkeep install --agent opencode       # planı göster (dry run)
engramkeep install --agent opencode --apply
engramkeep install --agent opencode --apply --mcp
engramkeep install --agent all --apply    # desteklenen tüm ajanlar
engramkeep install --agent opencode --uninstall
```

Ne yapar:

| Davranış | Ayrıntı |
| --- | --- |
| Managed block | Metin `<!-- engramkeep:begin -->` … `<!-- engramkeep:end -->` arasına yazılır; tekrar çalıştırma yalnızca bu bloğu günceller |
| Yedekler | Değişen her dosya yanına zaman damgalı `.bak` olarak kopyalanır ve yolu `manifest.json`'a yazılır |
| Kapsam | `--scope auto` (varsayılan; belgelenmişse global, değilse proje) veya `--scope project --project-dir YOL` |
| MCP kaydı | `--mcp` ile opt-in; Claude Code, OpenCode ve Cursor için otomatik, diğerlerinde gerekçesiyle atlanır |
| Kaldırma | `--uninstall` yalnızca managed bloğu siler, dosyanın kalanına dokunmaz |
| Dry run | Her hedef için `would-create`, `would-update` veya `would-remove` yazar |
| Üzerine yazmaz | Güvenle ayrıştıramadığı dosyaları düzenlemez; kullanıcı içeriğini silmez |

Desteklenen ajanlar: **OpenCode, Claude Code, OpenAI Codex, Cursor, Windsurf,
Gemini CLI, Antigravity, GitHub Copilot, Cline ve Roo Code.** `engramkeep
install --list` platforma göre tam hedef yollarını yazdırır.

---

## Hafıza nerede tutulur?

| Platform | Konum |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Engramkeep` |
| macOS | `~/Library/Application Support/Engramkeep` |
| Linux | `$XDG_DATA_HOME/engramkeep` veya `~/.local/share/engramkeep` |

`ENGRAMKEEP_HOME` ortam değişkeni veya global `--home` bayrağı ile
değiştirilebilir:

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

Bir proje kartı, küçük bir frontmatter bloğu olan Markdown'dır:

```markdown
---
id: example-project
title: Example Project
created: 2026-01-01T00:00:00Z
updated: 2026-01-02T12:00:00Z
tags: demo, docs
---

# Example Project

## Decisions

- Use SQLite for local storage.
```

---

## Arıza giderme kayıt defteri

Her ajan eninde sonunda aynı build hatasıyla iki kez karşılaşır. Engramkeep,
çözülen hatayı bir kez kaydeder; sonsuza kadar hatırlar:

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

Kayıtlar yazılmadan önce sır temizlemesinden geçer, dosya atomik olarak yeniden
yazılır ve ajanlara kayıtların **güvenilmeyen veri** olduğu — asla
çalıştırılacak talimat olmadığı — söylenir.

### Hatırlama ne kadar iyi?

Depo, 15 hata/çözüm çifti ve 45 bağımsız yazılmış sorgudan (İngilizce ve
Türkçe) oluşan sentetik bir korpus üzerinde tekrarlanabilir bir kıyaslama
içerir:

| Metrik | Sonuç |
| --- | --- |
| İlk sonuç doğruluğu | 43/45 (%95,6) |
| İlk üçte bulma | 45/45 (%100) |
| Türkçe sorgu → İngilizce kayıt, ilk sonuç | 15/15 (%100) |
| Ortalama karşılıklı sıra (MRR) | 0,978 |
| Sorgu gecikmesi p50 / p95 | ~4 ms / ~9 ms |

Puanlama sözlükseldir ve küçük bir çift dilli kavram bonusu içerir: embedding
yok, ağ çağrısı yok, indirilecek model yok. Eşleşmemesi gereken üç kontrol
sorgusundan ikisi boş döner; üçüncüsü [docs/BENCHMARK.md](docs/BENCHMARK.md)
dosyasında gizlenmeden raporlanır.

Yeniden üret:

```bash
python scripts/benchmark_fix_registry.py --output docs/BENCHMARK.md
```

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
| `engramkeep install [--list] [--agent AD] [--apply] [--uninstall] [--scope auto\|global\|project] [--mcp]` | Ajan entegrasyonunu planlar veya uygular |
| `engramkeep mcp [--status] [--allow-write]` | MCP stdio sunucusunu çalıştırır veya durumunu yazdırır |
| `engramkeep dashboard [--status] [--port PORT] [--allow-write]` | Yerel paneli çalıştırır veya durumunu yazdırır |

---

## Ajanlarla kullanım

Engramkeep iki taşınabilir dosya etrafında tasarlandı:

1. **`AGENTS.md`** — ajanlar arası ortak talimat formatı.
2. **`SKILL.md`** — OpenCode, Claude Code ve uyumlu ajanların kullandığı taşınabilir skill formatı.

Depoda hazır şablonlar var:

- [`skills/engramkeep/SKILL.md`](skills/engramkeep/SKILL.md)
- [`templates/agents/AGENTS.md`](templates/agents/AGENTS.md)
- [`templates/rules/`](templates/rules/) — Claude Code, Cursor, Windsurf, OpenCode

`engramkeep install --agent <ad> --apply` bunu senin için yapar; dilersen
şablonları elle de kopyalayabilirsin:

| Ajan | Tipik hedef |
| --- | --- |
| OpenCode | `~/.config/opencode/AGENTS.md` ve `~/.config/opencode/skills/engramkeep/SKILL.md` |
| Claude Code | `~/.claude/CLAUDE.md` ve `~/.claude/skills/engramkeep/SKILL.md` |
| Codex | `~/.codex/AGENTS.md` veya proje `AGENTS.md` |
| Cursor | `.cursor/rules/engramkeep.mdc` veya `AGENTS.md` |
| Windsurf | `.windsurf/rules/engramkeep.md` veya `AGENTS.md` |
| Gemini CLI / Antigravity | `GEMINI.md` veya `AGENTS.md` |
| Herhangi bir MCP istemcisi | `engramkeep mcp` (stdio) |

### MCP

Sunucuyu başlat:

```bash
engramkeep mcp
```

Sunucu, stdio üzerinden satır sonuyla ayrılmış JSON-RPC 2.0 ve `2025-11-25`
protokol sürümünü kullanır. Tipik bir istemci yapılandırması:

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

Varsayılan araç seti salt-okunurdur: `engramkeep_search`, `engramkeep_show`,
`engramkeep_list`, `engramkeep_recent`, `engramkeep_doctor` ve
`engramkeep_fixes`. Yazma araçlarını (`engramkeep_remember`,
`engramkeep_record_fix`) açmak için sunucuyu `--allow-write` ile başlat:

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

MCP üzerinden unutma (forget) aracı yoktur. Yıkıcı işlemler için CLI
kullanılmalı ve açık onay istenmelidir. Taşıma, protokol sürümü ve yazma modu
için `engramkeep mcp --status` çalıştır.

### Panel

Yerel paneli başlat:

```bash
engramkeep dashboard
```

Panel `127.0.0.1` adresine bağlanır ve fragment içinde oturum token'ı bulunan
bir URL yazdırır. Token HTML'e gömülmez; tarayıcı onu `sessionStorage` içinde
tutar ve `X-Engramkeep-Token` başlığıyla gönderir.

Panel varsayılan olarak salt-okunurdur. Hatırlama formunu açmak için:

```bash
engramkeep dashboard --allow-write
```

Yazmalar yalnızca POST ile ve `confirm: true` ile yapılır. Unutma (forget)
düğmesi yoktur. Boş bir port için `--port 0` kullan; makine tarafından
okunabilir güvenlik bilgisi için `engramkeep dashboard --status` çalıştır.

---

## Neden Mem0 / Basic Memory / vektör veritabanı değil?

| | Engramkeep | Bulut hafıza servisleri | Vektör DB yığınları |
| --- | --- | --- | --- |
| Depolama | Senin dosyaların, düz Markdown | Onların sunucuları | Yerel/uzak veritabanı |
| Bağımlılıklar | **0** (stdlib) | Hesap + API | Embedding + DB |
| Hatırlama modeli | Anahtar kelime + yenilik + EN/TR kavram genişletmesi | LLM/embedding | Anlamsal benzerlik |
| Denetlenebilirlik | `git diff`, herhangi bir editörde aç | Sınırlı | Opak vektörler |
| Ajan kurulumu | Tek komut, yedekli, geri alınabilir | Değişir | Özel yapıştırıcı kod |
| Güvenlik modeli | Hafıza veridir, asla talimat değil | Değişir | Değişir |
| En uygun | Kalıcı proje kararları, arıza kayıt defteri | Takım/barındırılan kullanım | Büyük korpuslar |

Küçük, denetlenebilir ve taşınabilir bir hafıza istiyorsan Engramkeep doğru
araçtır; bir RAG hattına ihtiyacın varsa değil.

---

## Güvenlik ve gizlilik

- **Varsayılan olarak yerel.** Çekirdek ağ çağrısı yapmaz, telemetri toplamaz.
- **Sırlar yazılmadan önce temizlenir.** API anahtarları, token'lar, şifreler, JWT'ler ve özel anahtarlar `[REDACTED]` ile değiştirilir.
- **Yol hapsi.** Proje adları `safe_join()` ile çözülür; hafıza dizininin dışına çıkamaz.
- **Atomik yazma.** Kartlar ve üretilen dosyalar geçici dosya + `os.replace()` ile yazılır; kayıt defteri de aynı şekilde yazılır.
- **Hafıza güvenilmeyen veridir.** Ajanlar hafıza kartlarındaki veya arıza kaydındaki komutları veya talimatları asla çalıştırmamalıdır.
- **Kurulum güvenliği.** Varsayılan dry run, yalnızca managed block, zaman damgalı yedek, `manifest.json` ve geri alınabilir kaldırma.
- **Otomatik Git push, bulut yükleme, junction veya arka plan daemon'u yok.** Bu özellikler kasıtlı olarak dışarıda tutuldu.
- **MCP yereldir ve varsayılan olarak salt-okunurdur.** Stdio kullanır, ağ dinleyicisi açmaz, unutma aracı sunmaz, yazma araçlarını yalnızca `--allow-write` ile açar.
- **Panel yalnızca loopback'te ve token korumalı.** `127.0.0.1`, oturum başına token, sıkı CSP, metin olarak işleme, yalnızca `--allow-write` + açık onay ile yazma.

Hassas bir ortamda kullanmadan önce [docs/PRIVACY.md](docs/PRIVACY.md) ve
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) dosyalarını oku.

---

## Kapsam dışı

- Git, issue tracker veya dokümantasyon sitesinin yerini almak.
- Sır, kimlik bilgisi veya düzenlemeye tabi kişisel veri saklamak.
- Her ajandan otomatik transkript toplamak. (Salt-okunur, onay tabanlı transkript adaptörleri [yol haritasında](docs/ROADMAP.md).)
- Barındırılan bir servis veya vektör veritabanı olmak.
- Kusursuz hatırlama. Hafıza, kaydettiğin kadar iyidir.

---

## Proje yapısı

```text
engramkeep/
├── AGENTS.md
├── README.md
├── README.tr.md
├── LICENSE
├── pyproject.toml
├── src/engramkeep/
│   ├── cli.py
│   ├── config.py
│   ├── concepts.py        # çift dilli EN/TR kavram genişletmesi
│   ├── models.py
│   ├── paths.py
│   ├── redact.py
│   ├── search.py
│   ├── store.py
│   ├── troubleshoot.py    # arıza kayıt defteri (TROUBLESHOOTING.md)
│   ├── mcp_server.py      # MCP stdio sunucusu
│   ├── dashboard.py       # sertleştirilmiş yerel panel
│   ├── installer.py       # yedekli, managed-block ajan kurulumu
│   └── adapters/          # gelecekteki transkript adaptörleri
├── assets/                # dashboard.png, demo.gif
├── examples/
│   ├── brain/             # minimal geçerli depo
│   ├── demo-brain/        # üretilmiş sentetik depo
│   ├── demo-cards.json
│   └── fix-registry/      # kıyaslama korpusu
├── scripts/
│   ├── build_demo_brain.py
│   └── benchmark_fix_registry.py
├── skills/engramkeep/SKILL.md
├── templates/
├── tests/                 # 203 test
├── docs/
└── .github/
```

---

## Katkı ve lisans

Katkılar memnuniyetle karşılanır. [CONTRIBUTING.md](CONTRIBUTING.md) ile başla,
[Code of Conduct](CODE_OF_CONDUCT.md) kurallarına uy ve güvenlik sorunlarını
[SECURITY.md](SECURITY.md) üzerinden bildir. Yeni başlayanlar için görevler:
[docs/GOOD_FIRST_ISSUES.md](docs/GOOD_FIRST_ISSUES.md).

MIT lisansı. Bkz. [LICENSE](LICENSE).

Engramkeep; Google, Anthropic, OpenAI, Anysphere, Cognition veya başka bir ajan
sağlayıcısıyla bağlantılı değildir. Bkz. [TRADEMARKS.md](TRADEMARKS.md).
