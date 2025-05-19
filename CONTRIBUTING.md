# Contributing to Attachments

First off, thank you for considering contributing to Attachments! It's people like you that make Attachments such a great tool.

This document provides guidelines for contributing to the project. Please feel free to propose changes to this document in a pull request.

## Ways to Contribute

- Reporting bugs
- Suggesting enhancements
- Writing documentation
- Submitting pull requests for code changes

## Getting Started

- Ensure you have a [GitHub account](https://github.com/signup/free).
- Fork the repository on GitHub.
- Clone your fork locally: `git clone https://github.com/YOUR_USERNAME/attachments.git`
- Create a new branch for your changes: `git checkout -b your-branch-name`

## Development Environment Setup

This project uses Python and `uv` for managing dependencies within a virtual environment.

1.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    # On Windows, use: .venv\Scripts\activate
    ```

2.  **Install dependencies:**
    ```bash
    uv pip install -e '.[dev]'
    ```

## Documentation

The project documentation is built using [MyST Markdown](https://mystmd.org/) and the `mystmd` command-line tool.

### Documentation Setup

The necessary tools for documentation (including `mystmd`) are installed as part of the development dependencies (see "Development Environment Setup" above).

### Building Documentation Locally

1.  **Ensure your virtual environment is activated** and dependencies are installed.
2.  **Build the documentation:**
    From the project root directory, run:
    ```bash
    myst build --html
    ```
    This command builds the documentation and usually starts a local web server (e.g., at `http://localhost:3000` or a similar port). The build output is generated in the `_build/html/` directory at the project root.

### Editing Documentation Content

-   **Page Content:** Documentation source files are primarily located in the `docs/` directory (e.g., `docs/index.md`, `docs/api_reference.md`). These are written in MyST Markdown.
-   **Site Structure & Configuration:** The main configuration for the documentation site, including the overall Table of Contents (TOC) and navigation, is in the `myst.yml` file at the project root.
    -   To update the main Table of Contents based on the files in `docs/` and `README.md`, you can run:
        ```bash
        myst init --write-toc
        ```
        This will update the `toc:` section in `myst.yml`.

### Key Documentation Files

-   `myst.yml`: (Project Root) Defines the project structure, site metadata, navigation, and the global Table of Contents.
-   `docs/index.md`: The main landing page for the documentation section of the site.
-   `docs/api_reference.md`: Placeholder for detailed API documentation.
-   `README.md`: (Project Root) Also included in the documentation site.

### Deployment

Documentation is automatically built and deployed to GitHub Pages whenever changes are pushed to the `main` branch. This is handled by the GitHub Actions workflow defined in `.github/workflows/deploy-docs.yml`.

## Submitting Changes

1.  Commit your changes: `git commit -m "Your descriptive commit message"`
2.  Push to your fork: `git push origin your-branch-name`
3.  Open a pull request on the original repository.

## Coding Standards

- Please ensure your code lints and tests pass before submitting a pull request.
- (Add any specific coding style guidelines here, e.g., Black, Flake8)

## Testing

Run tests using:
```bash
uv run pytest
```

## Releasing a New Version (Publishing to PyPI)

This project uses GitHub Actions to automate building and publishing the package to PyPI when a new version tag is pushed.

1.  **Update Version:** Update the `version` in `pyproject.toml` (e.g., `version = "0.2.5"`).
2.  **Commit Changes:** Commit the version update: `git commit -am "Bump version to 0.2.5"`
3.  **Create Git Tag:** Tag the commit with the same version, prefixed by `v`: `git tag v0.2.5`
4.  **Push Tag:** Push the tag to GitHub: `git push origin v0.2.5`

This will trigger the workflow defined in `.github/workflows/publish-to-pypi.yml`.

**Note on PyPI Token:** The publishing workflow requires a PyPI API token stored as a GitHub secret named `PYPI_API_TOKEN`. Ensure this is configured in the repository settings under "Secrets and variables" > "Actions".

Thank you for your contribution! 