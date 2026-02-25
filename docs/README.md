# Formbricks Documentation

This documentation is built using Mintlify. Here's how to run it locally and contribute.

## Prerequisites

- [Node.js](https://nodejs.org/) >= 20.17.0 (LTS versions recommended)

## Local Development

1. Install the [Mintlify CLI](https://www.npmjs.com/package/mintlify):

```bash
npm i -g mintlify
```

> **Note:** Requires Node.js ≥20.17.0 (LTS versions recommended). The `mintlify` package (v4.2.378) is the primary CLI. An alternative scoped package `@mintlify/cli` (v4.0.712) is also available.

2. Clone the Formbricks repository and navigate to the docs folder:

```bash
git clone https://github.com/formbricks/formbricks.git
cd formbricks/docs
```

3. Run the documentation locally:

```bash
mintlify dev
```

The documentation will be available at `http://localhost:3000`.

### Contributing

1. Create a new branch for your changes
2. Make your documentation updates
3. Submit a pull request to the main repository

### Troubleshooting

- If Mintlify dev isn't running, try `mintlify install` to reinstall dependencies
- If a page loads as a 404, ensure you're in the `docs` folder with the `docs.json` file
- For other issues, please check our [Contributing Guidelines](https://github.com/formbricks/formbricks/blob/main/CONTRIBUTING.md)

### Useful Commands

- `mintlify dev` — Start local documentation preview at `http://localhost:3000`
- `mintlify dev --port 3333` — Start on a custom port
- `mint check-links` — Check for broken internal links
- `mint check-links --check-anchors` — Check broken links including anchor references
- `mint a11y` — Run accessibility audit (contrast ratios, alt text)
- `mint openapi-check` — Validate OpenAPI specification files
- `mint validate --strict` — Strict build validation for CI/CD
