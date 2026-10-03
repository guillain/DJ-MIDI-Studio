# 📚 DJ MIDI Studio documentation

> Two doors: **End user** for DJs using the app, **Developer** for people
> working on its code. Everything is local and bundled with the app.

📍 Docs

![DJ MIDI Studio dashboard](images/layout/dashboard.png)

## Table of Contents

- [Choose your path](#choose-your-path)
- [Documentation map](#documentation-map)
- [Page template](#page-template)
- [In this section](#in-this-section)

## Choose your path

| I am… | Start here |
| --- | --- |
| 🎧 A DJ who wants to use the app | [End user documentation](enduser/README.md) |
| 🛠️ A developer or contributor | [Developer documentation](developer/README.md) |

| I want to… | Go to |
| --- | --- |
| Install and start | [User guide → Install](enduser/user-guide.md#install) |
| See what the app can do | [Features](enduser/features/README.md) |
| Know if my controller is supported | [Supported controllers](enduser/controller-profiles.md) |
| Run the code from source | [Quickstart](developer/setup/quickstart.md) |
| Understand the architecture | [Architecture](developer/design/architecture.md) |
| Prepare a release | [Release checklist](developer/cicd/release-checklist.md) |

## Documentation map

```text
docs/
├── README.md                     ← you are here
├── enduser/                      DJs
│   ├── README.md                 feature showcase
│   ├── user-guide.md             install, first launch, everyday workflow
│   ├── examples.md               step-by-step recipes
│   ├── controller-profiles.md    supported controllers
│   ├── midi-clock-compatibility.md
│   ├── plugins.md
│   └── features/                 one page per feature
├── developer/                    contributors
│   ├── README.md                 services overview
│   ├── workflow.md, contributing.md
│   ├── setup/                    quickstart, developer setup
│   ├── design/                   architecture, plugin manifest, evolution
│   ├── cicd/                     tests, quality gates, build, release
│   └── agent/                    AI-assisted development
└── images/                       screenshots (generated) and galleries
```

Controller manuals and MIDI message lists live in
[`controllers/`](../controllers/README.md); DJ-software format research in
[`software/`](../software/README.md).

## Page template

Every page follows the same shape, so you always know where to look:

1. `# Title` with an emoji, then a one-paragraph `>` summary;
2. a `📍` breadcrumb back to every parent index;
3. a `## Table of Contents`;
4. the content;
5. a `## Related` section (feature and guide pages) or an
   `## In this section` table (every `README.md` index).

Every directory has a `README.md` index. `tests/test_docs.py` checks the
template and that every relative link resolves.

## In this section

| Page | What it covers |
| --- | --- |
| [End user](enduser/README.md) | Features, user guide, recipes, supported controllers |
| [Developer](developer/README.md) | Services, design, setup, CI/CD, AI-assisted development |
| [Images](images/README.md) | Screenshot indexes and how they are generated |
