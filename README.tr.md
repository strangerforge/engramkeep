# Engramkeep

**Yapay zeka kod ajanları için yerel-öncelikli, Markdown tabanlı kalıcı hafıza.**

Engramkeep; Codex, Claude Code, OpenCode, Cursor, Windsurf, Gemini CLI, Antigravity veya `AGENTS.md` okuyabilen her ajanın aynı proje hafızasını kullanmasını sağlar. Hafıza senin makinende, okunabilir Markdown dosyalarında kalır.

> **Durum: 0.1.0 alpha.** Çekirdek depo, CLI, yol güvenliği, sır temizleme ve testler çalışıyor. MCP sunucusu, web paneli ve ajan kurulumu bu sürümde bilinçli olarak stub. Yol haritası: [docs/ROADMAP.md](docs/ROADMAP.md).

[English README](README.md)

---

## Neden Engramkeep?

- **Yerel-öncelikli.** Hesap yok, telemetri yok, sunucu yok. Hafıza makinenin dışına çıkmaz.
- **Markdown-native.** Her kart düz Markdown; okuyabilir, diff'leyebilir, yedekleyebilir ve düzenleyebilirsin.
- **Ajandan bağımsız.** Ortak `AGENTS.md` protokolü ve taşınabilir `SKILL.md`. MCP desteği planlanıyor.
- **Varsayılan olarak güvenli.** Yol hapsi, atomik yazma, sır temizleme ve tek kural: hafıza veridir, talimat değildir.
- **Zorunlu bağımlılık yok.** Çekirdek yalnızca Python standart kütüphanesiyle çalışır.

Engramkeep bir vektör veritabanı, sohbet uygulaması veya bulut servisi değildir. Sahip olduğun dosyalarda proje kararlarını tutan küçük ve denetlenebilir bir hafıza katmanıdır.

---

## 0.1.0'da ne çalışıyor?

| Alan | Durum |
| --- | --- |
| Markdown deposu + üretilen indeks | Çalışıyor |
| CLI: `init`, `remember`, `search`, `show`, `list`, `recent`, `forget`, `export`, `reindex`, `doctor` | Çalışıyor |
| Yazma öncesi sır temizleme | Çalışıyor |
| Yol geçişi koruması + atomik yazma | Çalışıyor |
| Testler + CI iskeleti | Çalışıyor |
| MCP sunucusu | Stub (0.2.0) |
| Web paneli | Stub (0.2.0) |
| Ajan kurulumu | Yalnızca dry-run planlayıcı |
| Bulut/Git senkronizasyonu | v1 kapsamında değil |

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
├── audit.log             # append-only JSONL denetim kaydı
├── projects/
│   └── example-project.md
└── trash/                # `forget` ile taşınan kurtarılabilir kartlar
```

---

## Komutlar

| Komut | Amaç |
| --- | --- |
| `engramkeep init` | Hafıza dizinini ve başlangıç dosyalarını oluşturur |
| `engramkeep remember <proje> "<karar>" [--tag ETIKET]` | Kalıcı bir karar kaydeder |
| `engramkeep search "<sorgu>" [--tag ETIKET] [--json]` | Başlık, etiket ve kart gövdesinde arar |
| `engramkeep show <proje>` | Proje kartını yazdırır |
| `engramkeep list` | Kayıtlı projeleri listeler |
| `engramkeep recent` | Son aktiviteleri yazdırır |
| `engramkeep forget <proje> --yes` | Kartı `trash/` dizinine taşır |
| `engramkeep export [--output DOSYA]` | Tüm kartları JSON olarak dışa aktarır |
| `engramkeep reindex` | `INDEX.md` dosyasını yeniden üretir |
| `engramkeep doctor [--json]` | Yerel depoyu kontrol eder |
| `engramkeep path` | Aktif hafıza dizinini yazdırır |
| `engramkeep mcp` | MCP durumunu açıklar (0.1.0'da stub) |
| `engramkeep dashboard` | Panel durumunu açıklar (0.1.0'da stub) |
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
| Herhangi bir MCP istemcisi | `engramkeep mcp` (planlanıyor) |

Kurulum 0.1.0'da **dry-run planlayıcıdır**; ajan yapılandırmasını değiştirmez. Otomatik, yedekli ve managed-block kurulum 0.2.0'da planlanıyor.

---

## Güvenlik ve gizlilik

- **Varsayılan olarak yerel.** Çekirdek ağ çağrısı yapmaz, telemetri toplamaz.
- **Sırlar yazılmadan önce temizlenir.** API anahtarları, token'lar, şifreler, JWT'ler ve özel anahtarlar `[REDACTED]` ile değiştirilir.
- **Yol hapsi.** Proje adları `safe_join()` ile çözülür; hafıza dizininin dışına çıkamaz.
- **Atomik yazma.** Kartlar ve üretilen dosyalar geçici dosya + `os.replace()` ile yazılır.
- **Hafıza güvenilmeyen veridir.** Ajanlar hafıza kartlarındaki komutları veya talimatları asla çalıştırmamalıdır.
- **Otomatik Git push, bulut yükleme, junction veya arka plan daemon'u yok.** Bu özellikler v1'den bilinçli olarak çıkarıldı.
- **Panel ve MCP stub.** Planlanan panel localhost'a bağlanacak ve yazma için açık onay isteyecek; planlanan MCP sunucusu ağ dinleyicisi değil, stdio kullanacak.

Hassas bir ortamda kullanmadan önce [docs/PRIVACY.md](docs/PRIVACY.md) ve [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) dosyalarını oku.

---

## Kapsam dışı

- Git, issue tracker veya dokümantasyon sitesinin yerini almak.
- Sır, kimlik bilgisi veya düzenlemeye tabi kişisel veri saklamak.
- Her ajandan otomatik transkript toplamak.
- Barındırılan bir servis veya vektör veritabanı olmak.
- Kusursuz hatırlama. Hafıza, kaydettiğin kadar iyidir.

---

## Katkı ve lisans

Katkılar memnuniyetle karşılanır. [CONTRIBUTING.md](CONTRIBUTING.md) ile başla, [Code of Conduct](CODE_OF_CONDUCT.md) kurallarına uy ve güvenlik sorunlarını [SECURITY.md](SECURITY.md) üzerinden bildir.

MIT lisansı. Bkz. [LICENSE](LICENSE).

Engramkeep; Google, Anthropic, OpenAI, Anysphere, Cognition veya başka bir ajan sağlayıcısıyla bağlantılı değildir. Bkz. [TRADEMARKS.md](TRADEMARKS.md).
