# BulkBite operations

BulkBite is a custom Frappe stock application for prepared-meal production. It does not depend on ERPNext. The custom app owns item identity, locations, recipes, planned demand, receipts, production use, physical audits, stock balances, evidence review, and accountant exports.

## Local development

The bench lives at `/home/keenan/BulkBite` and the site is `bulkbite.localhost`.

```bash
cd /home/keenan/BulkBite
bench start
```

The Vue source lives in `apps/bulkbite/frontend` and builds into the Frappe route at `/bulkbite`.

The Vue project is Desyium-owned. Select component and block owners through Desyium before adding interface source. Frappe UI owns forms and operational controls. shadcn-vue may fill jobs that Frappe UI does not own.

## Operational boundary

- Approved custom recipes define expected ingredient use.
- Receipt posting appends one stock event per reviewed line and is idempotent.
- Production runs accept either quantity used or quantity left, then append ingredient and finished-meal stock events on submission.
- Worker document extraction creates review drafts only. A person must approve rows before they can update a production draft or stock-audit draft.
- Physical counts remain drafts until a manager approves the reconciliation.
- Stock events and truth events are append-only through application controls and hash linked for tamper evidence. This is not a claim of legal or cryptographic immutability.
- Accounting categories exist only on exports. BulkBite does not post a general ledger or decide tax treatment.

## Spreadsheet intake

`bulkbite.theory_import.import_master_sheet` imports the controlled ingredient, approved recipe, and relative four-week planning theory from `Master Sheet.xlsx`. Relative weeks stay relative unless the workbook supplies calendar dates.

## Roles

- `BulkBite Worker`: enter receipts, record production use, upload worker evidence, and prepare physical counts.
- `BulkBite Manager`: maintain masters, approve production and reconciliation, and export operational records.
- `BulkBite Accountant`: read and export reviewed receipts, stock events, closing stock, and evidence.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench install-app bulkbite
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/bulkbite
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade
### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

agpl-3.0
