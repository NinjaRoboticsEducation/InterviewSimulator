# InterviewWikiTemplate

<div align="center">

**Turn Your Personal Knowledge into a Reliable Career Development and Interview Consultant**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![AI: Codex + More](https://img.shields.io/badge/AI-Codex%20%7C%20Antigravity%20%7C%20Claude%20%7C%20Cursor-purple.svg)](#agent-skills)
[![Local First](https://img.shields.io/badge/candidate%20data-local--first-orange.svg)](#privacy-and-safety)
[![Bilingual Resume](https://img.shields.io/badge/resume-English%20%2B%20Japanese-e60023.svg)](#generated-results)

[English](#english) · [日本語](#japanese) · [繁體中文](#traditional-chinese) · [简体中文](#simplified-chinese)

</div>

---

> [!NOTE]
> **New here?** Choose a language above and follow its Quick Start Guide. The examples use OpenAI Codex, but the same workflow can be used with Google Antigravity, Claude Code, Cursor, and other AI coding tools that can read the project instructions and skills.

<a id="english"></a>

# English

## Introduction

### What is InterviewWikiTemplate?

InterviewWikiTemplate is a reusable, local-first workspace that helps an AI coding tool act as your **personal career development and interview consultant**. It combines two connected knowledge systems:

- **PersonalWiki** stores your real career history: roles, responsibilities, achievements, skills, education, portfolio work, and personal introduction.
- **InterviewWiki** studies a specific opportunity and produces grounded career advice, compatibility analysis, interview preparation, and tailored English and Japanese resumes.

The important idea is simple: the AI should not guess who you are. It should first build a reliable candidate-fact index from information you supplied, then connect those facts to the requirements of a real role. This separation makes the results easier to trust, review, and reuse.

```text
Your source material                  Private candidate knowledge
PersonalWiki/raw/  ────────────────→ PersonalWiki/wiki/
                                              │
                                              ▼
                                     candidate-facts index
                                              │
Public job and company material               │
JobDescriptions/<company>/<role>/ ────────────┤
                                              ▼
                              analysis, interview preparation,
                              bilingual HTML resume and optional PDF
                                              │
                                              ▼
                                  Output/<company>/<role>/
```

### How the Personal Wiki makes the consultant reliable

A **Personal Wiki** is a structured knowledge base about you. Source files remain in `PersonalWiki/raw/`; reviewed, linked wiki pages live in `PersonalWiki/wiki/`. Important statements can point back to their source instead of relying on a temporary chat memory.

InterviewWikiTemplate is built on the **LLMWiki** concept. An **LLM (Large Language Model)** is the AI system that understands and generates language. An LLM Wiki gives that AI a durable, organized set of Markdown files to consult across sessions. Markdown is a simple text format that remains readable without special software.

The project keeps four kinds of information separate:

| Layer | Purpose | AI writing allowed? |
|---|---|---|
| `PersonalWiki/raw/` | Your original resume, portfolio, notes, and media | No; originals remain untouched |
| `PersonalWiki/wiki/` | Reviewed personal knowledge built from your sources | Only through the PersonalWiki review workflow |
| `.interviewwiki/` | Rebuildable local indexes and workflow state | Yes; generated runtime data |
| `Output/` | Opportunity-specific analysis and preparation | Yes; never treated as personal truth |

Generated resumes and interview answers never become candidate facts automatically. If your career information changes, update the PersonalWiki source material, review the wiki, and rebuild the candidate-fact index.

---

## Quick Start Guide

### Before you begin

Install [Git](https://git-scm.com/) for version history and recovery, and [uv](https://docs.astral.sh/uv/) for Python and project dependencies. Python 3.11 or newer is required; `uv` can manage the Python environment for you. Open the copied project folder in an AI coding tool such as OpenAI Codex.

The commands below are useful for verification. You can also ask Codex to run them for you in natural language.

### 1. Copy and initialize the application

Copy `InterviewWikiTemplate` to any location and rename the copy, for example `MyInterviewWiki`. Do not work in the clean template if you want to keep it reusable.

```bash
cd MyInterviewWiki
uv sync --locked
uv run --locked interviewwiki init
uv run --locked interviewwiki doctor
uv run --locked pytest
```

Then open the folder as a project in Codex. A good first prompt is:

```text
Read AGENTS.md and the project skills. Initialize this InterviewWiki project,
run its health checks and tests, and explain any issue in plain language.
Do not add invented candidate facts or modify my PersonalWiki source files.
```

### 2. Initialize and build your resume and portfolio PersonalWiki

This is normally a one-time setup. Repeat it only when you add or change personal source material.

Place your original information under `PersonalWiki/raw/`:

| Folder | Suggested content |
|---|---|
| `PersonalWiki/raw/articles/` | Resume, professional biography, career history |
| `PersonalWiki/raw/notes/` | Skills, responsibilities, achievements, interview notes |
| `PersonalWiki/raw/papers/` | Certificates or other formal records |
| `PersonalWiki/raw/media/` | Portfolio images and one profile photo |

For automatic profile-photo detection, use one of these exact names:

- `PersonalWiki/raw/media/Profile.png`
- `PersonalWiki/raw/media/Profile.jpg`
- `PersonalWiki/raw/media/Profile.jpeg`

Initialize and check the PersonalWiki:

```bash
cd PersonalWiki
uv sync --locked --all-extras
uv run --locked llmwiki init
uv run --locked llmwiki doctor
```

Return to the InterviewWiki project root, then ask Codex:

```text
Review the PersonalWiki instructions, discover the source files under
PersonalWiki/raw/, and build or update my personal resume and portfolio wiki.
Preserve every original source file. Check important career claims against the
sources, run normal and strict wiki lint, and give me a clear walkthrough of
the pages created, evidence used, uncertainties found, and validation results.
Never place job-tailored or generated InterviewWiki content into PersonalWiki.
```

Review the walkthrough carefully. Correct missing dates, unclear ownership, inflated wording, or unsupported claims in the PersonalWiki before continuing.

### 3. Build the local candidate-fact index

This migration does **not** move, rewrite, or delete your wiki. It reads approved candidate-source pages and creates a rebuildable index used by the interview workflows.

```text
Use the candidate-migrate skill to rebuild the candidate-fact index from my
PersonalWiki. Execute the migration and validation without pausing for approval.
Do not modify PersonalWiki and never use generated resumes, job-specific output,
or prior interview preparation as candidate truth. Return a detailed walkthrough
showing accepted sources, excluded files, facts indexed, warnings, and checks.
```

Run this step after the initial PersonalWiki setup and whenever you update personal information. You do not need to run it for every new job if the PersonalWiki has not changed.

### 4. Add a job description

Create one folder per company and opportunity. This supports multiple roles at the same company and repeat applications.

```text
JobDescriptions/
└── ExampleCompany/
    └── senior-product-designer/
        ├── JobDescription.md
        └── notes.md                 # Optional public role-related input
```

Paste the job description into `JobDescription.md`. You may add other public, job-related Markdown files in the same folder. Do not put personal information there.

### 5. Ask Codex to register and research the opportunity

From the InterviewWiki project root, prompt Codex:

```text
I added a new opportunity at
JobDescriptions/ExampleCompany/senior-product-designer/JobDescription.md.
Use the opportunity-register and opportunity-ingest skills to register and
ingest it. Then use company-research to research the company and role using
public sources. Save the captured research under this opportunity, include
source links and access dates, and clearly label facts, inference, and unknowns.
Never send or expose any PersonalWiki or candidate-fact content during external
research. Run the opportunity checks and give me a detailed walkthrough.
```

Registration gives the opportunity a stable identity. Ingestion turns the source material into structured requirements. Company research adds current public context without sharing private candidate data.

### 6. Generate compatibility analysis or the complete package

For a focused compatibility review:

```text
Use candidate-query and compatibility-review for
ExampleCompany/senior-product-designer. Compare the role requirements with my
grounded candidate facts. Identify strong matches, partial matches, evidence
gaps, risks, and practical recommendations. Cite the local candidate evidence
for every personal claim. Do not change PersonalWiki and do not invent facts.
```

For the complete interview preparation package:

```text
Prepare the complete interview package for
ExampleCompany/senior-product-designer. Use the relevant project skills to
produce a grounded experience audit and compatibility review, company and role
briefing, interview questions and evidence-based answer guidance, preparation
plan, and tailored English and Japanese resumes. Render the required bilingual
HTML resumes and the optional PDFs. Use my detected profile photo when present.
Validate the full package strictly, fix safe generation issues, and give me a
walkthrough of outputs, evidence coverage, uncertainties, and remaining actions.
Never modify PersonalWiki or turn generated content into candidate truth.
```

Generated files appear under `Output/ExampleCompany/senior-product-designer/`.

### 7. Review the result

Open the HTML resumes in a browser and inspect any PDFs at A4 size. Check names, dates, links, profile photo, responsibilities, achievements, early-career history, and translations. Also review every evidence gap or uncertainty reported by the agent.

Useful final checks are:

```bash
uv run --locked interviewwiki task validate ExampleCompany/senior-product-designer --kind full-package --strict
uv run --locked interviewwiki task finalize ExampleCompany/senior-product-designer --kind full-package
```

---

## InterviewWikiTemplate Specification

### Key Features

| Feature | What it provides |
|---|---|
| PersonalWiki grounding | Career claims come from your reviewed source material instead of AI guesswork |
| Local-first candidate processing | Personal information stays in the local workspace during normal processing |
| Privacy-separated research | External research uses company and role queries, never PersonalWiki content |
| Opportunity registry | Keeps each company and role isolated and repeatable |
| Requirement ingestion | Converts job descriptions into structured, traceable requirements |
| Compatibility review | Distinguishes strong matches, partial matches, evidence gaps, and genuine risks |
| Interview preparation | Builds role-specific questions, answer guidance, and preparation actions |
| Method-style resume | Produces consistently structured English and Japanese HTML resumes |
| Profile-photo support | Detects `Profile.png`, `Profile.jpg`, or `Profile.jpeg` automatically |
| Optional PDF automation | Renders print-ready A4 PDFs while keeping HTML as the required output |
| Strict validation | Checks structure, evidence use, privacy boundaries, and package completeness |
| Portable design | Uses project-relative paths so the whole folder can be copied elsewhere |

### File Structure Diagram

```text
InterviewWikiTemplate/
├── AGENTS.md                    # Main operating and safety rules for AI agents
├── README.md                    # This multilingual guide
├── interviewwiki.yaml           # Paths, privacy, workflow, resume, and palette settings
├── pyproject.toml / uv.lock     # Application package and locked dependencies
├── PersonalWiki/                # Private, reusable candidate knowledge system
│   ├── raw/                     # User-provided originals; never generated job output
│   │   └── media/Profile.*      # Optional automatically detected profile photo
│   └── wiki/                    # Reviewed resume and portfolio knowledge pages
├── JobDescriptions/             # One isolated input area per opportunity
│   └── <company>/<opportunity>/
├── Output/                      # Generated analysis, preparation, HTML, and PDFs
│   └── <company>/<opportunity>/
├── .interviewwiki/              # Rebuildable local indexes and workflow state
├── .agents/
│   ├── rules/                   # Shared agent policies
│   ├── workflows/               # Guided end-to-end workflows
│   └── skills/                  # Nine focused workflow skills
├── prompts/                     # Reusable prompt guidance
├── schemas/                     # Machine-readable input and output contracts
├── templates/
│   ├── Method/                  # Reference resume content and visual design
│   └── resume/method-v1/        # Production resume renderer assets
├── src/interviewwiki/           # Python command-line application
├── tests/                       # Portability, privacy, workflow, and rendering checks
└── docs/                        # Additional architecture and usage documentation
```

`JobDescriptions/`, `Output/`, and `.interviewwiki/` contain user or generated runtime data in a working copy. A distributable template should keep these areas free of test candidate outputs.

### Workflow Overview

#### Workflow A — Personal knowledge setup

1. You place authentic source material in `PersonalWiki/raw/`.
2. The PersonalWiki workflow registers, normalizes, links, and reviews it.
3. Wiki lint checks structure, provenance, links, and semantic review status.
4. `candidate-migrate` builds `.interviewwiki/candidate-facts.json` from approved candidate sources.
5. PersonalWiki remains the authority; the fact index can be deleted and rebuilt.

#### Workflow B — Opportunity registration and research

1. You add a job description under `JobDescriptions/<company>/<opportunity>/`.
2. `opportunity-register` confirms identity, paths, and prerequisites.
3. `opportunity-ingest` extracts role requirements and preserves their provenance.
4. `company-research` gathers public company and role context.
5. Research is saved with sources while private candidate content remains local and excluded from queries.

#### Workflow C — Analysis and interview preparation

1. `candidate-query` retrieves only relevant, supported candidate facts.
2. `compatibility-review` maps evidence to each job requirement.
3. `interview-prepare` produces the experience audit, briefing, questions, answer guidance, and action plan.
4. Gaps remain gaps; generated wording is not promoted into personal history.

#### Workflow D — Resume generation and validation

1. `resume-render` creates English and Japanese Method-style HTML resumes.
2. The renderer includes a supported profile photo automatically and can create A4 PDFs.
3. `interview-validate` checks required files, structure, grounding, and workflow state.
4. Finalization records that the package passed the configured checks; it does not certify that every statement is true without human review.

<a id="agent-skills"></a>

### Agent Skills

An **agent skill** is a focused instruction set that tells an AI coding tool how to perform one part of the workflow safely and consistently.

| Skill | When it is used | Main responsibility |
|---|---|---|
| `candidate-migrate` | After PersonalWiki setup or an update | Builds the local fact index from approved personal sources; excludes generated outputs |
| `candidate-query` | Before analysis or writing | Retrieves relevant facts with source references and reports missing evidence |
| `company-research` | During opportunity registration or refresh | Collects public company and role information without exposing candidate data |
| `compatibility-review` | For fit analysis | Maps grounded candidate evidence to requirements, risks, and recommendations |
| `interview-prepare` | For a focused task or full package | Produces preparation materials using job evidence and candidate facts |
| `interview-validate` | Before delivery or finalization | Checks package completeness, grounding, structure, and strict workflow gates |
| `opportunity-ingest` | After a job description is added | Converts source documents into traceable structured role requirements |
| `opportunity-register` | At the start of a new role workflow | Creates or verifies the company/opportunity identity and required directories |
| `resume-render` | When resumes are requested | Generates Method-style bilingual HTML and optional A4 PDFs with photo support |

### Generated Results

A complete package can include:

- a role and company briefing;
- candidate experience and compatibility analysis;
- strengths, gaps, risks, and improvement actions;
- role-specific interview questions and answer guidance;
- preparation checklists and discussion points;
- tailored English and Japanese HTML resumes;
- optional English and Japanese A4 PDFs;
- validation and execution records.

In a strictly validated resume, every detailed recent role has two or three distinct, evidence-grounded bullets under both Responsibilities and Key Achievements. Self PR explains practical interest and career direction through real experience and at least one concrete project, portfolio case, responsibility, or achievement. Standard headings and selectable text remain ATS-readable; relevant keywords are used only when personal evidence supports them.

Exact filenames are controlled by the workflow and schemas. Treat all generated material as a draft for human review, especially translations, inferred motivation, and suggested interview answers.

<a id="privacy-and-safety"></a>

### Privacy and Safety

- Candidate processing is local-first.
- External research receives company and role queries only.
- PersonalWiki content must never be included in external research prompts.
- Original files under `PersonalWiki/raw/` remain untouched.
- Opportunity-specific output never becomes PersonalWiki truth automatically.
- Candidate facts must be supported by approved personal sources.
- Missing evidence is reported instead of invented.
- All paths are relative to the project so a copied workspace remains portable.

### Useful Commands

```bash
# Project health
uv run --locked interviewwiki doctor
uv run --locked interviewwiki personal status
uv run --locked interviewwiki candidate status

# Candidate facts
uv run --locked interviewwiki candidate migrate

# Opportunity lifecycle
uv run --locked interviewwiki opportunity register <company>/<opportunity>
uv run --locked interviewwiki task prepare <company>/<opportunity> --kind full-package

# Resume and validation
uv run --locked interviewwiki resume render <company>/<opportunity> --pdf all
uv run --locked interviewwiki task validate <company>/<opportunity> --kind full-package --strict
uv run --locked interviewwiki task finalize <company>/<opportunity> --kind full-package

# Application tests
uv run --locked pytest
```

[Back to language menu](#interviewwikitemplate)

---

<a id="japanese"></a>

# 日本語

## はじめに

### InterviewWikiTemplate とは

InterviewWikiTemplate は、AI コーディングツールを自分専用の**キャリア開発・面接対策コンサルタント**として活用するための、再利用可能なローカル優先ワークスペースです。次の二つの知識システムを連携させます。

- **PersonalWiki**：実際の職歴、担当業務、実績、スキル、学歴、ポートフォリオ、自己紹介を保管します。
- **InterviewWiki**：応募先ごとに求人を分析し、適合度評価、面接対策、英語・日本語の履歴書を作成します。

重要なのは、AI に経歴を推測させないことです。ユーザーが提供した情報から信頼できる候補者ファクトを構築し、それを求人要件と結び付けます。

```text
本人が提供した資料                   再利用できる候補者知識
PersonalWiki/raw/ ───────────────→ PersonalWiki/wiki/
                                             │
                                             ▼
                                     candidate-facts 索引
                                             │
公開された求人・企業情報                    │
JobDescriptions/<企業>/<職種>/ ─────────────┤
                                             ▼
                              適合度分析、面接対策、
                              日英 HTML 履歴書、任意の PDF
                                             │
                                             ▼
                                  Output/<企業>/<職種>/
```

### Personal Wiki が信頼性を高める仕組み

**Personal Wiki** は、自分についての構造化された知識ベースです。原本は `PersonalWiki/raw/`、確認・整理されたページは `PersonalWiki/wiki/` に置かれます。重要な記述を一時的なチャット記憶ではなく、根拠資料に結び付けられます。

この仕組みは **LLMWiki** の考え方を利用します。**LLM（大規模言語モデル）**とは、文章を理解・生成する AI です。LLM Wiki は、複数のセッションで AI が参照できる、整理された Markdown（特別なソフトがなくても読めるテキスト形式）の知識を提供します。

| 領域 | 目的 | 生成内容の扱い |
|---|---|---|
| `PersonalWiki/raw/` | 履歴書、ポートフォリオ、メモ、画像の原本 | AI は原本を書き換えない |
| `PersonalWiki/wiki/` | 根拠を確認した個人知識 | PersonalWiki のレビューフローのみで更新 |
| `.interviewwiki/` | 再構築可能な索引と実行状態 | 生成されるランタイムデータ |
| `Output/` | 求人別の分析・面接対策 | 個人情報の正本として再利用しない |

生成した履歴書や回答例が、自動的に候補者の事実へ混入することはありません。経歴を更新したときは PersonalWiki を見直し、候補者ファクト索引を再構築します。

---

## クイックスタートガイド

### 事前準備

履歴管理と復元に [Git](https://git-scm.com/)、Python と依存関係の管理に [uv](https://docs.astral.sh/uv/) を使用します。Python 3.11 以降が必要です。コピーしたプロジェクトを OpenAI Codex などの AI コーディングツールで開いてください。

### 1. アプリケーションをコピーして初期化する

クリーンな `InterviewWikiTemplate` を任意の場所へコピーし、`MyInterviewWiki` などに改名します。再利用用テンプレートを直接作業場所にしないでください。

```bash
cd MyInterviewWiki
uv sync --locked
uv run --locked interviewwiki init
uv run --locked interviewwiki doctor
uv run --locked pytest
```

Codex へのプロンプト例：

```text
AGENTS.md とプロジェクトの skills を読み、この InterviewWiki を初期化してください。
ヘルスチェックとテストを実行し、問題を分かりやすく説明してください。
候補者情報を推測したり、PersonalWiki の原本を変更したりしないでください。
```

### 2. 履歴書・ポートフォリオの PersonalWiki を構築する

通常は初回のみ行い、個人資料を追加・変更したときに更新します。原本を `PersonalWiki/raw/` 配下へ配置します。

| フォルダー | 内容の例 |
|---|---|
| `raw/articles/` | 履歴書、職務経歴、プロフィール |
| `raw/notes/` | スキル、担当業務、実績、面接メモ |
| `raw/papers/` | 証明書などの正式資料 |
| `raw/media/` | ポートフォリオ画像とプロフィール写真 |

写真を自動検出するには、`PersonalWiki/raw/media/Profile.png`、`Profile.jpg`、または `Profile.jpeg` を使用します。

```bash
cd PersonalWiki
uv sync --locked --all-extras
uv run --locked llmwiki init
uv run --locked llmwiki doctor
```

プロジェクトルートに戻り、Codex に依頼します。

```text
PersonalWiki の指示を読み、PersonalWiki/raw/ の資料から履歴書・
ポートフォリオ Wiki を構築または更新してください。原本はすべて保持し、
重要な経歴を根拠と照合してください。通常 lint と strict lint を実行し、
作成ページ、使用した根拠、不確実な点、検証結果を詳しく報告してください。
求人向けの生成物を PersonalWiki に入れないでください。
```

### 3. 候補者ファクト索引を構築する

この処理は Wiki の移動や書き換えではありません。承認済みの個人情報を読み、面接ワークフロー用の再構築可能な索引を作ります。

```text
candidate-migrate skill を使い、PersonalWiki から候補者ファクト索引を
再構築・検証してください。PersonalWiki を変更せず、生成済み履歴書や
求人別出力を候補者の事実に使用しないでください。採用した資料、除外した
ファイル、索引化した事実、警告、検証結果の詳細を報告してください。
```

初回と PersonalWiki 更新後に実行します。個人情報に変更がなければ、新しい求人ごとに実行する必要はありません。

### 4. 求人情報を追加する

企業・求人ごとにフォルダーを作り、求人票を Markdown で保存します。

```text
JobDescriptions/
└── ExampleCompany/
    └── senior-product-designer/
        ├── JobDescription.md
        └── notes.md                 # 任意の公開求人関連メモ
```

### 5. Codex に登録・取り込み・企業調査を依頼する

```text
JobDescriptions/ExampleCompany/senior-product-designer/JobDescription.md に
新しい求人を追加しました。opportunity-register と opportunity-ingest で
登録・取り込みを行い、company-research で企業と職種を公開情報から調査して
ください。出典リンクと参照日を保存し、事実・推論・不明点を区別してください。
外部調査に PersonalWiki や候補者ファクトを送信しないでください。
```

### 6. 適合度分析または完全パッケージを生成する

適合度分析のみ：

```text
ExampleCompany/senior-product-designer に candidate-query と
compatibility-review を使用してください。求人要件と根拠のある候補者情報を
比較し、強い一致、部分一致、根拠不足、リスク、改善提案を示してください。
個人に関する記述にはローカルの根拠を付け、PersonalWiki を変更しないでください。
```

完全パッケージ：

```text
ExampleCompany/senior-product-designer の完全な面接準備パッケージを作成して
ください。経験監査、適合度分析、企業・職種概要、想定質問と根拠に基づく回答
ガイド、準備計画、英語・日本語の履歴書を生成してください。日英 HTML は必須、
PDF は自動生成し、写真があれば使用してください。strict 検証を実行し、成果物、
根拠、不確実な点、残作業を報告してください。PersonalWiki は変更しないでください。
```

成果物は `Output/ExampleCompany/senior-product-designer/` に保存されます。HTML と A4 PDF を開き、氏名、日付、リンク、写真、担当業務、実績、初期キャリア、翻訳を確認してください。

---

## InterviewWikiTemplate 仕様

### 主な機能

| 機能 | 内容 |
|---|---|
| PersonalWiki による根拠付け | AI の推測ではなく、確認済み個人資料から経歴を使用 |
| ローカル優先処理 | 候補者情報を通常の処理ではローカルに保持 |
| 分離された外部調査 | 企業・職種だけを調べ、PersonalWiki を外部へ送らない |
| 求人別管理 | `<企業>/<求人>` 単位で入力・出力を分離 |
| 適合度分析 | 一致、部分一致、根拠不足、リスクを区別 |
| 面接準備 | 求人別の質問、回答ガイド、準備行動を作成 |
| Method スタイル履歴書 | 統一構成の日英 HTML 履歴書を生成 |
| 写真・PDF 対応 | 写真を自動検出し、任意で A4 PDF を生成 |
| 厳格な検証 | 根拠、プライバシー、構造、完全性を確認 |
| 可搬性 | プロジェクト相対パスにより任意の場所へコピー可能 |

### ファイル構成図

```text
InterviewWikiTemplate/
├── AGENTS.md                    # AI エージェントの運用・安全ルール
├── interviewwiki.yaml           # パス、プライバシー、履歴書設定
├── PersonalWiki/                # 非公開の候補者知識
│   ├── raw/                     # ユーザー原本
│   └── wiki/                    # 確認・整理済みの個人ページ
├── JobDescriptions/             # <企業>/<求人> ごとの入力
├── Output/                      # 求人別の生成物
├── .interviewwiki/              # 再構築可能な索引と実行状態
├── .agents/skills/              # 9 個の専門 skill
├── prompts/ / schemas/          # プロンプトとデータ契約
├── templates/Method/            # 履歴書デザインの参照例
├── templates/resume/method-v1/  # 本番用履歴書テンプレート
├── src/interviewwiki/           # コマンドラインアプリ
├── tests/                       # 安全性・動作・可搬性テスト
└── docs/                        # 補足技術資料
```

### ワークフロー概要

1. **個人知識の準備：** 原本を PersonalWiki に追加し、登録・整理・根拠確認・lint を行います。
2. **候補者索引：** `candidate-migrate` が承認済み資料からローカル索引を構築します。
3. **求人登録：** 求人を追加し、`opportunity-register` と `opportunity-ingest` で要件を構造化します。
4. **公開調査：** `company-research` が候補者情報を使わず企業・職種を調査します。
5. **分析：** `candidate-query` と `compatibility-review` が根拠と要件を対応付けます。
6. **面接対策：** `interview-prepare` が質問、回答ガイド、準備計画を作成します。
7. **履歴書：** `resume-render` が日英 HTML と任意の PDF を生成します。
8. **検証：** `interview-validate` が成果物の完全性と根拠を確認します。

### Agent Skills

**Agent skill** は、AI ツールが特定の作業を安全かつ一貫して行うための専用指示です。

| Skill | 役割 |
|---|---|
| `candidate-migrate` | PersonalWiki から候補者ファクト索引を構築し、生成物を除外 |
| `candidate-query` | 分析に必要な個人情報を根拠付きで検索 |
| `company-research` | 候補者情報を公開せず、企業・職種の公開情報を収集 |
| `compatibility-review` | 求人要件と個人の根拠を比較し、適合度と不足を評価 |
| `interview-prepare` | 面接準備資料と完全パッケージを作成 |
| `interview-validate` | 構造、根拠、完全性、ワークフロー状態を検証 |
| `opportunity-ingest` | 求人資料を追跡可能な構造化要件へ変換 |
| `opportunity-register` | 企業・求人 ID と必要フォルダーを登録・確認 |
| `resume-render` | 写真対応の日英 HTML と A4 PDF を生成 |

### 生成される内容

完全パッケージには、企業・職種概要、経験監査、適合度分析、強みとギャップ、想定質問、回答ガイド、準備チェックリスト、日英 HTML 履歴書、任意の A4 PDF、検証記録を含められます。strict 検証済みの履歴書では、詳細表示する各直近職歴に「担当業務」と「主な実績」をそれぞれ根拠付きで 2～3 項目記載します。自己 PR は、実務上の志望理由とキャリアの方向性を、具体的なプロジェクト、ポートフォリオ、担当業務、または実績に結び付けます。標準見出しと選択可能なテキストを保ち、ATS（採用管理システム）が読み取りやすい構成にします。生成内容は必ず人が確認する下書きとして扱ってください。

### プライバシーと安全性

- 候補者情報の処理はローカル優先です。
- 外部調査には企業名・職種名・公開検索語だけを使用します。
- `PersonalWiki/raw/` の原本は変更しません。
- 求人別の生成物を候補者の事実へ自動的に混入しません。
- 根拠がない場合は推測せず、不足として報告します。
- すべて相対パスで扱うため、フォルダーごと移動できます。

[言語メニューに戻る](#interviewwikitemplate)

---

<a id="traditional-chinese"></a>

# 繁體中文

## 簡介

### 什麼是 InterviewWikiTemplate？

InterviewWikiTemplate 是一個可重複使用、以本機處理為優先的工作空間，協助 AI 程式開發工具成為你的**個人職涯發展與面試顧問**。它連接兩套知識系統：

- **PersonalWiki**：保存你真實的職涯經歷、工作職責、成果、技能、教育、作品集與自我介紹。
- **InterviewWiki**：針對個別職缺進行研究，產生適配度分析、面試準備，以及英文與日文履歷。

核心原則很簡單：AI 不應猜測你的背景。系統先從你提供的資料建立可信的候選人事實索引，再把這些事實與真實職缺需求連結。

```text
你提供的原始資料                    可重複使用的個人知識
PersonalWiki/raw/ ───────────────→ PersonalWiki/wiki/
                                             │
                                             ▼
                                     candidate-facts 索引
                                             │
公開職缺與公司資料                         │
JobDescriptions/<公司>/<職缺>/ ────────────┤
                                             ▼
                              適配度分析、面試準備、
                              英日 HTML 履歷與選用 PDF
                                             │
                                             ▼
                                  Output/<公司>/<職缺>/
```

### Personal Wiki 如何提高可靠性

**Personal Wiki** 是一個關於你的結構化知識庫。原始檔案保留在 `PersonalWiki/raw/`，經過整理與審查的頁面位於 `PersonalWiki/wiki/`。重要敘述可以連回證據，而不是依賴短暫的聊天記憶。

本專案採用 **LLMWiki** 概念。**LLM（大型語言模型）**是能理解與產生文字的 AI。LLM Wiki 提供一組有組織、可跨工作階段查閱的 Markdown 檔案；Markdown 是不需特殊軟體也能閱讀的純文字格式。

| 區域 | 用途 | 產生內容的規則 |
|---|---|---|
| `PersonalWiki/raw/` | 你的履歷、作品集、筆記與媒體原檔 | AI 不改寫原檔 |
| `PersonalWiki/wiki/` | 由來源建立並審查的個人知識 | 只透過 PersonalWiki 審查流程更新 |
| `.interviewwiki/` | 可重建的索引與工作流程狀態 | 執行期間產生 |
| `Output/` | 針對職缺的分析與準備材料 | 不可自動當作個人事實 |

產生的履歷或面試答案不會自動混入你的 PersonalWiki。當個人資料更新時，應先更新並審查 PersonalWiki，再重建候選人事實索引。

---

## 快速開始指南

### 開始之前

請安裝 [Git](https://git-scm.com/) 以管理版本與復原紀錄，以及 [uv](https://docs.astral.sh/uv/) 以管理 Python 和相依套件。需要 Python 3.11 或更新版本。接著用 OpenAI Codex 等 AI 程式開發工具開啟複製後的專案。

### 1. 複製並初始化應用程式

把乾淨的 `InterviewWikiTemplate` 複製到任何位置，並改名為 `MyInterviewWiki` 等名稱。若要保留範本供未來使用，請勿直接在原範本工作。

```bash
cd MyInterviewWiki
uv sync --locked
uv run --locked interviewwiki init
uv run --locked interviewwiki doctor
uv run --locked pytest
```

Codex 提示詞範例：

```text
請閱讀 AGENTS.md 和專案 skills，初始化這個 InterviewWiki，執行健康檢查
與測試，並用簡單文字解釋任何問題。不要虛構候選人事實，也不要修改
PersonalWiki 的原始資料。
```

### 2. 初始化並建立個人履歷與作品集 Wiki

這通常只需在第一次執行；新增或修改個人資料後再重做。將原始資料放在 `PersonalWiki/raw/`：

| 資料夾 | 建議內容 |
|---|---|
| `raw/articles/` | 履歷、職涯經歷、個人簡介 |
| `raw/notes/` | 技能、職責、成果、面試筆記 |
| `raw/papers/` | 證書或其他正式文件 |
| `raw/media/` | 作品集圖片與個人照片 |

若要自動偵測個人照片，請使用 `PersonalWiki/raw/media/Profile.png`、`Profile.jpg` 或 `Profile.jpeg`。

```bash
cd PersonalWiki
uv sync --locked --all-extras
uv run --locked llmwiki init
uv run --locked llmwiki doctor
```

回到專案根目錄後，對 Codex 輸入：

```text
請閱讀 PersonalWiki 的操作規則，從 PersonalWiki/raw/ 建立或更新我的履歷與
作品集 Wiki。保留所有原始檔，將重要職涯敘述與來源核對，執行一般與 strict
wiki lint，並詳細說明建立的頁面、使用的證據、不確定內容和驗證結果。
絕不可把針對職缺產生的內容放入 PersonalWiki。
```

### 3. 建立本機候選人事實索引

這個遷移不會移動、重寫或刪除 Wiki。它只讀取獲准的個人來源，建立面試工作流程所需、可重建的索引。

```text
請使用 candidate-migrate skill，從 PersonalWiki 重建並驗證候選人事實索引。
不要修改 PersonalWiki，也不要把產生的履歷、職缺輸出或舊面試內容當作個人
事實。請詳細回報採用的來源、排除的檔案、建立的事實、警告與檢查結果。
```

第一次設定及每次更新 PersonalWiki 後執行。若個人資料沒有變更，不需為每個新職缺重做。

### 4. 新增職缺說明

為每間公司與每個職缺建立獨立資料夾，並用 Markdown 保存職缺內容。

```text
JobDescriptions/
└── ExampleCompany/
    └── senior-product-designer/
        ├── JobDescription.md
        └── notes.md                 # 選用的公開職缺相關筆記
```

### 5. 請 Codex 註冊、匯入並研究職缺

```text
我已新增 JobDescriptions/ExampleCompany/senior-product-designer/JobDescription.md。
請使用 opportunity-register 與 opportunity-ingest 註冊及匯入職缺，再使用
company-research 從公開來源研究公司與職位。保存來源連結與查閱日期，清楚區分
事實、推論和未知資訊。外部研究不可傳送或揭露任何 PersonalWiki 或候選人事實。
完成檢查後提供詳細執行說明。
```

### 6. 產生適配度分析或完整準備套件

只做適配度分析：

```text
請對 ExampleCompany/senior-product-designer 使用 candidate-query 和
compatibility-review。比較職缺需求與有證據的個人事實，列出高度符合、部分
符合、證據缺口、風險及實用建議。每項個人敘述都要引用本機來源，不可修改
PersonalWiki 或虛構事實。
```

產生完整套件：

```text
請為 ExampleCompany/senior-product-designer 製作完整面試準備套件，包含經驗
審查與適配度分析、公司與職位摘要、面試問題和有證據的回答指引、準備計畫，
以及英文與日文履歷。英日 HTML 為必要輸出，並自動產生選用 PDF；若偵測到照片
請納入履歷。執行 strict 驗證並回報成果、證據、不確定內容和後續行動。
不可修改 PersonalWiki 或把產生內容變成個人事實。
```

結果位於 `Output/ExampleCompany/senior-product-designer/`。請檢查 HTML 與 A4 PDF 中的姓名、日期、連結、照片、職責、成果、早期經歷及翻譯。

---

## InterviewWikiTemplate 規格

### 主要功能

| 功能 | 說明 |
|---|---|
| PersonalWiki 證據基礎 | 使用經過審查的個人資料，不讓 AI 猜測經歷 |
| 本機優先處理 | 一般處理期間，個人資訊留在本機工作空間 |
| 隱私隔離研究 | 外部只查公司與職位，不傳送 PersonalWiki |
| 職缺註冊 | 依 `<公司>/<職缺>` 隔離並管理每次申請 |
| 需求匯入 | 將職缺說明轉換成可追溯的結構化需求 |
| 適配度分析 | 區分高度符合、部分符合、證據缺口與風險 |
| 面試準備 | 產生專屬問題、回答指引與準備行動 |
| Method 風格履歷 | 產生結構一致的英文與日文 HTML 履歷 |
| 照片及 PDF | 自動偵測照片，並可產生適合 A4 的 PDF |
| 嚴格驗證 | 檢查結構、證據、隱私界線與完整性 |
| 可攜設計 | 使用專案相對路徑，可將整個資料夾移至他處 |

### 檔案結構圖

```text
InterviewWikiTemplate/
├── AGENTS.md                    # AI 代理的操作與安全規則
├── interviewwiki.yaml           # 路徑、隱私、工作流程與履歷設定
├── PersonalWiki/                # 私人的候選人知識系統
│   ├── raw/                     # 使用者提供的原始檔
│   └── wiki/                    # 已整理與審查的個人知識
├── JobDescriptions/             # <公司>/<職缺> 輸入資料
├── Output/                      # 各職缺產生的結果
├── .interviewwiki/              # 可重建索引與執行狀態
├── .agents/skills/              # 九個專用工作 skills
├── prompts/ / schemas/          # 提示指引與資料規格
├── templates/Method/            # 履歷內容與視覺參考
├── templates/resume/method-v1/  # 正式履歷產生範本
├── src/interviewwiki/           # 命令列應用程式
├── tests/                       # 隱私、流程、可攜性與顯示測試
└── docs/                        # 補充技術文件
```

### 工作流程總覽

1. **個人知識：** 將原始資料放入 PersonalWiki，進行登錄、整理、證據審查與 lint（自動內容檢查）。
2. **候選人索引：** `candidate-migrate` 從獲准來源建立本機索引。
3. **職缺註冊：** `opportunity-register` 與 `opportunity-ingest` 登錄職缺並結構化需求。
4. **公開研究：** `company-research` 在不使用私人資料的情況下研究公司與職位。
5. **適配度分析：** `candidate-query` 與 `compatibility-review` 將個人證據對應到需求。
6. **面試準備：** `interview-prepare` 產生問題、回答指引與準備計畫。
7. **履歷產生：** `resume-render` 建立英日 HTML 及選用 PDF。
8. **品質驗證：** `interview-validate` 檢查完整性、結構與證據。

### Agent Skills

**Agent skill** 是讓 AI 工具能安全、一致完成特定工作的專用操作指引。

| Skill | 主要用途 |
|---|---|
| `candidate-migrate` | 從 PersonalWiki 建立候選人事實索引，排除生成內容 |
| `candidate-query` | 以來源引用查詢分析所需的個人事實 |
| `company-research` | 不揭露個人資訊，只研究公開公司與職位資料 |
| `compatibility-review` | 比較職缺需求與個人證據，分析優勢與缺口 |
| `interview-prepare` | 建立單項面試材料或完整準備套件 |
| `interview-validate` | 檢查成果結構、根據、完整性與流程狀態 |
| `opportunity-ingest` | 將職缺文件轉為可追溯的結構化需求 |
| `opportunity-register` | 建立或確認公司、職缺識別與必要目錄 |
| `resume-render` | 產生含照片的英日 HTML 與 A4 PDF |

### 產生結果

完整套件可包含公司與職位摘要、經驗審查、適配度分析、優勢與缺口、面試題目、回答指引、準備清單、英文與日文 HTML 履歷、選用 A4 PDF，以及驗證紀錄。通過 strict 驗證的履歷，會在每個詳細近期職位的「工作職責」與「主要成果」下各列出 2～3 項不同且有證據的內容。自我推薦會用具體專案、作品集案例、職責或成果，說明實際求職動機與職涯方向。標準標題與可選取文字可供 ATS（應徵者追蹤系統）清楚讀取。所有產生內容都應視為需要人工確認的草稿。

### 隱私與安全

- 候選人資料以本機處理為優先。
- 外部研究只使用公司、職位與公開搜尋詞。
- `PersonalWiki/raw/` 中的原始檔保持不變。
- 職缺產生內容不會自動成為 PersonalWiki 的事實。
- 缺少證據時會報告缺口，不會自行虛構。
- 使用相對路徑，因此整個專案可複製到任何位置。

[返回語言選單](#interviewwikitemplate)

---

<a id="simplified-chinese"></a>

# 简体中文

## 简介

### 什么是 InterviewWikiTemplate？

InterviewWikiTemplate 是一个可重复使用、以本地处理为优先的工作空间，帮助 AI 编程工具成为你的**个人职业发展与面试顾问**。它连接两套知识系统：

- **PersonalWiki**：保存你真实的职业经历、工作职责、成果、技能、教育、作品集和自我介绍。
- **InterviewWiki**：针对具体职位进行研究，生成匹配度分析、面试准备，以及英文和日文简历。

核心原则很简单：AI 不应猜测你的背景。系统先根据你提供的资料建立可信的候选人事实索引，再把这些事实与真实职位要求连接起来。

```text
你提供的原始资料                    可重复使用的个人知识
PersonalWiki/raw/ ───────────────→ PersonalWiki/wiki/
                                             │
                                             ▼
                                     candidate-facts 索引
                                             │
公开职位和公司资料                         │
JobDescriptions/<公司>/<职位>/ ────────────┤
                                             ▼
                              匹配度分析、面试准备、
                              英日 HTML 简历与可选 PDF
                                             │
                                             ▼
                                  Output/<公司>/<职位>/
```

### Personal Wiki 如何提高可靠性

**Personal Wiki** 是一个关于你的结构化知识库。原始文件保存在 `PersonalWiki/raw/`，经过整理和审核的页面位于 `PersonalWiki/wiki/`。重要陈述可以连接回证据，而不是依赖短暂的聊天记忆。

本项目采用 **LLMWiki** 概念。**LLM（大型语言模型）**是能够理解和生成文字的 AI。LLM Wiki 提供一组有组织、可跨工作会话查阅的 Markdown 文件；Markdown 是无需特殊软件也能阅读的纯文本格式。

| 区域 | 用途 | 生成内容规则 |
|---|---|---|
| `PersonalWiki/raw/` | 你的简历、作品集、笔记和媒体原件 | AI 不改写原件 |
| `PersonalWiki/wiki/` | 根据来源建立并审核的个人知识 | 只通过 PersonalWiki 审核流程更新 |
| `.interviewwiki/` | 可重建的索引和工作流程状态 | 运行期间生成 |
| `Output/` | 针对职位的分析和准备材料 | 不可自动作为个人事实 |

生成的简历和面试答案不会自动混入 PersonalWiki。个人资料更新后，应先更新并审核 PersonalWiki，再重建候选人事实索引。

---

## 快速开始指南

### 开始之前

请安装 [Git](https://git-scm.com/) 以管理版本和恢复记录，以及 [uv](https://docs.astral.sh/uv/) 以管理 Python 和依赖包。需要 Python 3.11 或更高版本。然后使用 OpenAI Codex 等 AI 编程工具打开复制后的项目。

### 1. 复制并初始化应用

把干净的 `InterviewWikiTemplate` 复制到任意位置，并改名为 `MyInterviewWiki` 等名称。如果希望保留模板供未来使用，请勿直接在原模板中工作。

```bash
cd MyInterviewWiki
uv sync --locked
uv run --locked interviewwiki init
uv run --locked interviewwiki doctor
uv run --locked pytest
```

Codex 提示词示例：

```text
请阅读 AGENTS.md 和项目 skills，初始化这个 InterviewWiki，运行健康检查和
测试，并用简单语言解释任何问题。不要虚构候选人事实，也不要修改
PersonalWiki 的原始资料。
```

### 2. 初始化并建立个人简历和作品集 Wiki

这通常只需在首次使用时执行；新增或修改个人资料后再更新。将原始资料放在 `PersonalWiki/raw/`：

| 文件夹 | 建议内容 |
|---|---|
| `raw/articles/` | 简历、职业经历、个人简介 |
| `raw/notes/` | 技能、职责、成果、面试笔记 |
| `raw/papers/` | 证书或其他正式文件 |
| `raw/media/` | 作品集图片和个人照片 |

如需自动检测个人照片，请使用 `PersonalWiki/raw/media/Profile.png`、`Profile.jpg` 或 `Profile.jpeg`。

```bash
cd PersonalWiki
uv sync --locked --all-extras
uv run --locked llmwiki init
uv run --locked llmwiki doctor
```

返回项目根目录后，对 Codex 输入：

```text
请阅读 PersonalWiki 的操作规则，从 PersonalWiki/raw/ 建立或更新我的简历和
作品集 Wiki。保留所有原始文件，将重要职业陈述与来源核对，运行普通和 strict
wiki lint，并详细说明建立的页面、使用的证据、不确定内容和验证结果。
绝不能把针对职位生成的内容放入 PersonalWiki。
```

### 3. 建立本地候选人事实索引

这个迁移不会移动、重写或删除 Wiki。它只读取获准的个人来源，建立面试工作流程所需、可重建的索引。

```text
请使用 candidate-migrate skill，从 PersonalWiki 重建并验证候选人事实索引。
不要修改 PersonalWiki，也不要把生成的简历、职位输出或旧面试内容当作个人
事实。请详细报告采用的来源、排除的文件、建立的事实、警告和检查结果。
```

首次设置及每次更新 PersonalWiki 后执行。如果个人资料没有变化，不需要为每个新职位重复执行。

### 4. 添加职位说明

为每家公司和每个职位建立独立文件夹，并用 Markdown 保存职位内容。

```text
JobDescriptions/
└── ExampleCompany/
    └── senior-product-designer/
        ├── JobDescription.md
        └── notes.md                 # 可选的公开职位相关笔记
```

### 5. 请 Codex 注册、导入并研究职位

```text
我已添加 JobDescriptions/ExampleCompany/senior-product-designer/JobDescription.md。
请使用 opportunity-register 和 opportunity-ingest 注册并导入职位，再使用
company-research 从公开来源研究公司和职位。保存来源链接和查阅日期，清楚区分
事实、推断和未知信息。外部研究不得发送或泄露任何 PersonalWiki 或候选人事实。
完成检查后提供详细执行说明。
```

### 6. 生成匹配度分析或完整准备包

只做匹配度分析：

```text
请对 ExampleCompany/senior-product-designer 使用 candidate-query 和
compatibility-review。比较职位要求和有证据的个人事实，列出高度匹配、部分
匹配、证据缺口、风险和实用建议。每项个人陈述都要引用本地来源，不得修改
PersonalWiki 或虚构事实。
```

生成完整准备包：

```text
请为 ExampleCompany/senior-product-designer 制作完整面试准备包，包括经验审核
和匹配度分析、公司与职位摘要、面试问题和有证据的回答指导、准备计划，以及
英文和日文简历。英日 HTML 是必需输出，并自动生成可选 PDF；如果检测到照片，
请加入简历。运行 strict 验证并报告成果、证据、不确定内容和后续行动。
不得修改 PersonalWiki 或把生成内容变成个人事实。
```

结果位于 `Output/ExampleCompany/senior-product-designer/`。请检查 HTML 和 A4 PDF 中的姓名、日期、链接、照片、职责、成果、早期经历及翻译。

---

## InterviewWikiTemplate 规格

### 主要功能

| 功能 | 说明 |
|---|---|
| PersonalWiki 证据基础 | 使用经过审核的个人资料，不让 AI 猜测经历 |
| 本地优先处理 | 一般处理期间，个人信息留在本地工作空间 |
| 隐私隔离研究 | 外部只查询公司和职位，不发送 PersonalWiki |
| 职位注册 | 按 `<公司>/<职位>` 隔离并管理每次申请 |
| 要求导入 | 将职位说明转换为可追溯的结构化要求 |
| 匹配度分析 | 区分高度匹配、部分匹配、证据缺口和风险 |
| 面试准备 | 生成专属问题、回答指导和准备行动 |
| Method 风格简历 | 生成结构一致的英文和日文 HTML 简历 |
| 照片和 PDF | 自动检测照片，并可生成适合 A4 的 PDF |
| 严格验证 | 检查结构、证据、隐私边界和完整性 |
| 可移植设计 | 使用项目相对路径，可将整个文件夹移动到其他位置 |

### 文件结构图

```text
InterviewWikiTemplate/
├── AGENTS.md                    # AI 代理的操作和安全规则
├── interviewwiki.yaml           # 路径、隐私、工作流程和简历设置
├── PersonalWiki/                # 私有的候选人知识系统
│   ├── raw/                     # 用户提供的原始文件
│   └── wiki/                    # 已整理和审核的个人知识
├── JobDescriptions/             # <公司>/<职位> 输入资料
├── Output/                      # 各职位生成的结果
├── .interviewwiki/              # 可重建索引和运行状态
├── .agents/skills/              # 九个专用工作 skills
├── prompts/ / schemas/          # 提示指导和数据规范
├── templates/Method/            # 简历内容和视觉参考
├── templates/resume/method-v1/  # 正式简历生成模板
├── src/interviewwiki/           # 命令行应用
├── tests/                       # 隐私、流程、可移植性和显示测试
└── docs/                        # 补充技术文档
```

### 工作流程概览

1. **个人知识：** 将原始资料放入 PersonalWiki，进行登记、整理、证据审核和 lint（自动内容检查）。
2. **候选人索引：** `candidate-migrate` 从获准来源建立本地索引。
3. **职位注册：** `opportunity-register` 和 `opportunity-ingest` 登记职位并结构化要求。
4. **公开研究：** `company-research` 在不使用私人资料的情况下研究公司和职位。
5. **匹配分析：** `candidate-query` 和 `compatibility-review` 将个人证据对应到要求。
6. **面试准备：** `interview-prepare` 生成问题、回答指导和准备计划。
7. **简历生成：** `resume-render` 建立英日 HTML 和可选 PDF。
8. **质量验证：** `interview-validate` 检查完整性、结构和证据。

### Agent Skills

**Agent skill** 是让 AI 工具能够安全、一致完成特定工作的专用操作指南。

| Skill | 主要用途 |
|---|---|
| `candidate-migrate` | 从 PersonalWiki 建立候选人事实索引，排除生成内容 |
| `candidate-query` | 带来源引用查询分析所需的个人事实 |
| `company-research` | 不泄露个人信息，只研究公开公司和职位资料 |
| `compatibility-review` | 比较职位要求和个人证据，分析优势与缺口 |
| `interview-prepare` | 建立单项面试材料或完整准备包 |
| `interview-validate` | 检查成果结构、依据、完整性和流程状态 |
| `opportunity-ingest` | 将职位文件转换为可追溯的结构化要求 |
| `opportunity-register` | 建立或确认公司、职位标识和必要目录 |
| `resume-render` | 生成带照片的英日 HTML 和 A4 PDF |

### 生成结果

完整准备包可包含公司与职位摘要、经验审核、匹配度分析、优势与缺口、面试题、回答指导、准备清单、英文与日文 HTML 简历、可选 A4 PDF，以及验证记录。通过 strict 验证的简历，会在每个详细近期职位的“工作职责”和“主要成果”下各列出 2～3 项不同且有证据的内容。自我推荐会用具体项目、作品集案例、职责或成果，说明实际求职动机和职业发展方向。标准标题和可选择文字可供 ATS（申请人跟踪系统）清楚读取。所有生成内容都应视为需要人工确认的草稿。

### 隐私与安全

- 候选人资料以本地处理为优先。
- 外部研究只使用公司、职位和公开搜索词。
- `PersonalWiki/raw/` 中的原始文件保持不变。
- 职位生成内容不会自动成为 PersonalWiki 的事实。
- 缺少证据时会报告缺口，不会自行虚构。
- 使用相对路径，因此整个项目可复制到任意位置。

[返回语言菜单](#interviewwikitemplate)

<div align="center">

Made with ❤️ for helping advance your career development

</div>
