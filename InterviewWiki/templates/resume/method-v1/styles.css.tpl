:root {
  --paper: {{paper}}; --sheet: {{sheet}}; --ink: {{ink}}; --muted: {{muted}};
  --line: {{line}}; --soft-line: {{line}}; --panel: {{panel}}; --deep: {{deep}}; --deep-2: #3d3435; --accent: {{accent}};
  --accent-secondary: {{accent_secondary}}; --gold: {{gold}};
  --font: "Noto Sans", "Noto Sans JP", "Hiragino Kaku Gothic ProN", "Yu Gothic", Arial, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
html { font-size: 62.5%; }
body {
  margin: 0; color: var(--ink); font: 1.4rem/1.55 var(--font);
  background: linear-gradient(90deg, rgba(230,0,35,.045) 1px, transparent 1px),
    linear-gradient(0deg, rgba(11,119,127,.045) 1px, transparent 1px), var(--paper);
  background-size: 42px 42px;
}
a { color: inherit; text-decoration-color: var(--accent); text-underline-offset: .18em; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
.lang-toggle { position: sticky; top: 0; z-index: 10; display: flex; justify-content: center; gap: 8px; padding: 12px; background: rgba(255,247,246,.94); border-bottom: 1px solid var(--line); }
.lang-toggle button { border: 1px solid var(--deep); border-radius: 7px; padding: 8px 18px; color: var(--deep); background: transparent; cursor: pointer; font: 700 1.4rem var(--font); }
.lang-toggle button.active { color: #fff; background: var(--deep); }
.lang-toggle button:focus-visible { outline: 3px solid var(--accent-secondary); outline-offset: 2px; }
.resume-page { display: none; width: min(1120px, calc(100% - 32px)); margin: 24px auto 40px; background: var(--sheet); box-shadow: 0 28px 80px rgba(23,32,28,.14); }
.resume-page.active { display: grid; grid-template-columns: 292px minmax(0,1fr); align-items: stretch; }
.sidebar { padding: 30px 24px; color: #fff; background: linear-gradient(135deg, rgba(65,230,0,.08), transparent 34%), linear-gradient(315deg, rgba(11,119,127,.22), transparent 42%), var(--deep); }
.profile-photo, .profile-placeholder { display: grid; place-items: center; width: 212px; height: 212px; margin: 0 auto 18px; object-fit: cover; border: 3px solid rgba(255,255,255,.82); border-radius: 50%; background: var(--deep); box-shadow: 0 12px 32px rgba(0,0,0,.28); }
.profile-placeholder { color: #fff; font-size: 5rem; font-weight: 800; }
.name { margin: 0; color: #fff; font-size: 2.35rem; line-height: 1.12; text-align: center; overflow-wrap: normal; word-break: keep-all; }
.sidebar-section { padding-top: 16px; margin-top: 16px; border-top: 1px solid rgba(255,255,255,.17); }
.sidebar-title { margin: 0 0 10px; color: #fff; font-size: 12px; font-weight: 800; text-transform: uppercase; }
.contact-list, .tag-list, .award-list, .plain-list { padding: 0; margin: 0; list-style: none; }
.contact-list li { display: grid; grid-template-columns: 18px 1fr; gap: 8px; margin-bottom: 8px; color: #eff6f3; font-size: 12px; line-height: 1.35; overflow-wrap: anywhere; }
.contact-icon { width: 14px; height: 14px; margin-top: 2px; border-radius: 50%; background: #a8beb9; color: var(--deep); font-size: 8px; font-weight: 800; line-height: 14px; text-align: center; }
.tag-list { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-list li { padding: 4px 8px; color: #f8fbfa; background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.15); border-radius: 6px; font-size: 12px; line-height: 1.25; }
.plain-list li, .award-list li { margin-bottom: 7px; color: #eef5f2; font-size: 12px; line-height: 1.36; }
.plain-list .detail { color: #d4e1de; }
.award-list li { display: grid; grid-template-columns: 42px 1fr; gap: 7px; }
.award-list span { color: #f6c269; font-weight: 800; }
.lang-row { display: grid; grid-template-columns: 1fr auto; gap: 8px; margin-bottom: 8px; font-size: 12px; line-height: 1.35; }
.lang-row strong { color: #fff; }
.lang-row span { color: #d4e1de; text-align: right; }
.main { min-width: 0; padding: 34px 42px 42px; }
.headline { max-width: 760px; margin: 0; color: var(--ink); font-size: 3.4rem; line-height: 1.08; }
.main > .section, .main > section { margin-top: 28px; }
.section-heading { display: flex; align-items: baseline; gap: 12px; margin-bottom: 13px; border-bottom: 2px solid var(--deep); }
.section-heading h2 { margin: 0 0 7px; color: var(--ink); font-size: 1.8rem; line-height: 1.1; text-transform: uppercase; }
.main p { margin: 0 0 12px; color: var(--deep-2); font-size: 1.45rem; line-height: 1.58; }
.signal-strip { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 10px; margin-top: 22px; padding: 14px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.signal strong { display: block; color: var(--accent); font-size: 12px; line-height: 1.1; }
.signal span { display: block; margin-top: 5px; color: var(--muted); font-size: 12px; line-height: 1.35; }
.experience { position: relative; padding: 0 0 17px 20px; margin-bottom: 17px; border-left: 2px solid var(--soft-line); border-bottom: 1px solid var(--soft-line); }
.experience::before { content: ""; position: absolute; left: -5px; top: 2px; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.experience-header { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 12px; align-items: start; }
.experience-header h3, .earlier-career h3, .expertise-block h3 { margin: 0; color: var(--ink); font-size: 1.65rem; line-height: 1.18; }
.experience-header p { margin: 3px 0 0; color: var(--accent-secondary); font-size: 1.45rem; font-weight: 800; line-height: 1.3; }
.experience-header span { color: var(--muted); font-size: 1.4rem; font-weight: 700; line-height: 1.35; text-align: right; white-space: nowrap; }
.experience h4 { margin: 12px 0 6px; color: var(--gold); font-size: 1.4rem; font-weight: 800; text-transform: uppercase; }
.main ul { padding-left: 18px; margin: 0; }
.main li { margin-bottom: 5px; color: var(--deep-2); font-size: 1.4rem; line-height: 1.52; }
.claim-links { margin-left: .3em; font-size: .92em; }
.earlier-career { padding-top: 4px; }
.earlier-career h3 { margin-bottom: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
td, th { padding: 8px 7px; border-bottom: 1px solid var(--soft-line); font-size: 12px; line-height: 1.35; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 800; text-transform: uppercase; }
.expertise-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 14px 22px; }
.expertise-block { padding-top: 12px; border-top: 1px solid var(--line); }
.expertise-block h3 { margin-bottom: 6px; color: var(--accent-secondary); }
.self-pr { padding: 18px 20px; border: 1px solid var(--line); background: linear-gradient(135deg, rgba(230,0,35,.06), transparent 44%), var(--panel); }
.self-pr p:last-child { margin-bottom: 0; }
@media (max-width: 860px) {
  .resume-page.active { grid-template-columns: 1fr; }
  .main { padding: 28px 22px 34px; }
  .signal-strip, .expertise-grid { grid-template-columns: 1fr 1fr; }
  .experience-header { grid-template-columns: 1fr; }
  .experience-header span { text-align: left; white-space: normal; }
}
@media (max-width: 560px) {
  .resume-page { width: 100%; margin: 0; }
  .signal-strip, .expertise-grid { grid-template-columns: 1fr; }
  .headline { font-size: 2.6rem; }
}
@media print {
  :root { --print-safe-top: 26px; --print-safe-bottom: 30px; --print-page-break-pad: 36px; }
  @page { size: A4; margin: 0; }
  html { font-size: 75%; }
  body { position: relative; background: #fff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body::before { content: ""; position: fixed; inset: 0 auto 0 0; z-index: 0; width: 200px; height: 100vh; background: linear-gradient(135deg, rgba(65,230,0,.08), transparent 34%), linear-gradient(315deg, rgba(11,119,127,.22), transparent 42%), var(--deep); }
  .no-print, .lang-toggle, .sr-only { display: none !important; }
  .resume-page { display: none !important; }
  .resume-page.active { position: relative; z-index: 1; display: grid !important; grid-template-columns: 292px minmax(0,1fr); width: 1120px; margin: 0; padding: var(--print-safe-top) 0 var(--print-safe-bottom); background: transparent; box-shadow: none; zoom: .685; }
  .sidebar { padding: 30px 24px; background: transparent; }
  .main { padding: 34px 42px 42px; background: transparent; }
  .signal-strip { grid-template-columns: repeat(4,minmax(0,1fr)); margin-top: 20px; padding: 12px 0; }
  .experience-header { grid-template-columns: minmax(0,1fr) auto; }
  .experience-header span { text-align: right; white-space: nowrap; }
  .main > .section, .main > section { margin-top: 24px; }
  .main p { font-size: 1.34rem; margin-bottom: 10px; line-height: 1.45; }
  .main li { font-size: 1.24rem; margin-bottom: 2px; line-height: 1.36; }
  .experience { padding-bottom: 10px; margin-bottom: 10px; break-inside: avoid; page-break-inside: avoid; }
  #resume-en .experience:nth-of-type(4), #resume-ja .experience:nth-of-type(4) { break-before: page; page-break-before: always; padding-top: var(--print-page-break-pad); }
  #resume-en .experience:nth-of-type(4)::before, #resume-ja .experience:nth-of-type(4)::before { top: calc(var(--print-page-break-pad) + 2px); }
  #resume-en [data-section-id="self-pr"], #resume-ja [data-section-id="self-pr"] { break-before: page; page-break-before: always; padding-top: var(--print-page-break-pad); }
  .experience h4 { margin: 7px 0 3px; font-size: 1.25rem; }
  .experience-header h3, .earlier-career h3, .expertise-block h3 { font-size: 1.5rem; }
  .experience-header p { font-size: 1.3rem; }
  .experience-header span { font-size: 1.25rem; }
  td, th { padding: 6px 7px; }
  .self-pr { padding: 16px 18px; }
  .main p, .main li, .sidebar li, .lang-row, .signal, tr { break-inside: avoid; orphans: 3; widows: 3; }
  .section-heading, .experience-header, .experience h4, .earlier-career h3, .expertise-block h3 { break-after: avoid; }
  .self-pr, .expertise-block, .earlier-career, table, .expertise-grid { break-inside: avoid; page-break-inside: avoid; }
  .main p, .main li, .sidebar li, .lang-row, .signal, tr { page-break-inside: avoid; }
  .section-heading, .experience-header, .experience h4, .earlier-career h3, .expertise-block h3 { page-break-after: avoid; }
  .sidebar-title, .contact-list li, .tag-list li, .plain-list li, .award-list li, .lang-row, .signal strong, .signal span, table, td, th { font-size: 14.6px; }
  thead { display: table-row-group; }
  a { text-decoration: none; }
}
