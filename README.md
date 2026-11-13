<div align="center">

# bsystem's · source-coppy

**Ready-made websites, landing pages and SaaS templates. Copy, paste, ship.**

[![License: MIT](https://img.shields.io/badge/license-MIT-a3e635?style=for-the-badge)](LICENSE)
![Templates](https://img.shields.io/badge/templates-312+-1f2329?style=for-the-badge)
![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20PT--BR-a3e635?style=for-the-badge)
![Themes](https://img.shields.io/badge/themes-light%20%7C%20dim%20%7C%20dark-1f2329?style=for-the-badge)

[Features](#-features) · [Catalog](#-catalog) · [Quick start](#-quick-start) · [Contributing](#-contributing)

</div>

---

## ✨ Features

| | |
|---|---|
| 🧱 **312+ templates** | 104 websites, 104 landing pages, 104 SaaS — 78 niches × 4 styles |
| 🎨 **4 visual styles** | Minimal · Bold · Elegant · Neon |
| 🌗 **3 themes** | Light (default), Dim (soft dark) and Dark (strong) |
| 🌐 **Bilingual** | The whole platform *and* every exported template in English or Brazilian Portuguese |
| 📋 **Copy or download** | One click to copy a standalone HTML file — no build step needed |
| 🆓 **Open source** | MIT licensed, forever free |

## 📚 Catalog

<details>
<summary><b>🏪 Websites (26 niches)</b> — click to expand</summary>

Barbershop · Restaurant · Dental clinic · Gym · Bakery · Law firm · Real estate · Pet shop · Beauty salon · Coffee shop · Photographer · Church · School · Auto repair · Hotel · Architecture studio · Accounting · Tattoo studio · Pizzeria · Veterinary · Yoga studio · Florist · Construction · Psychologist · Nutritionist · Travel agency
</details>

<details>
<summary><b>🚀 Landing pages (26 niches)</b> — click to expand</summary>

E-book launch · Online course · Mobile app · Event · Webinar · Waitlist · Podcast · Digital agency · Coaching · Product launch · Newsletter · Mentorship · Freelancer · Nonprofit · Crypto project · Video game · Music album · Fitness program · Property launch · Insurance · Solar energy · Wedding · Store promo · Consulting · Hiring page · Fundraising
</details>

<details>
<summary><b>📊 SaaS (26 niches)</b> — click to expand</summary>

CRM · Analytics · Invoicing · Help desk · Scheduling · HR platform · Inventory · Project management · Email marketing · Point of sale · Learning platform · Fleet tracking · Clinic management · AI writer · Personal finance · Form builder · Chatbot · Uptime monitoring · Booking engine · Social scheduler · Contract manager · Restaurant OS · Gym management · Real estate CRM · Delivery platform · OKRs & goals
</details>

<details>
<summary><b>🎨 Styles</b></summary>

| Style | Vibe | Font |
|---|---|---|
| Minimal | Clean, airy, soft niche color | Figtree |
| Bold | Saturated background, hard edges | Bricolage Grotesque |
| Elegant | Warm neutrals, pill buttons | Fraunces |
| Neon | Dark canvas, glowing accent | JetBrains Mono |
</details>

## ⚡ Quick start

```bash
git clone https://github.com/brunnojob/source-coppy.git
cd source-coppy
bun install
bun run dev
```

<details>
<summary><b>🧭 How to use a template</b></summary>

1. Open the platform and pick a category (Websites, Landing pages, SaaS).
2. Search a niche — e.g. `barbershop` / `barbearia`.
3. Open a template, switch **EN / PT-BR** to choose the content language.
4. Click **Copy HTML** or **Download .html** and drop it on any static host.
</details>

<details>
<summary><b>🛠 Tech stack</b></summary>

- React 19 + TanStack Start / Router
- Tailwind CSS v4 with `oklch` design tokens
- Vite 7 · TypeScript · Vitest
</details>

<details>
<summary><b>➕ Adding a new niche</b></summary>

Edit `src/lib/templates.ts` and add an entry to `NICHES`:

```ts
n("sushi", "Sushi bar", "Restaurante japonês", 15),
```

Each niche automatically gets all 4 styles in both languages.
</details>

## 🤝 Contributing

Pull requests are welcome! Open an issue to suggest new niches, styles or languages.

## 📄 License

[MIT](LICENSE) © bsystem's
