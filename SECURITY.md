# Security Policy

## Supported Versions

The project is currently in early development. Security fixes are applied to the latest version on the default branch.

## Reporting a Vulnerability

Please report vulnerabilities through a private GitHub security advisory if available, or by contacting the repository owner directly.

Do not create public issues for vulnerabilities that expose credentials, sensitive data, or exploitable code paths.

## Security Notes

- The app does not require API keys.
- Do not commit `.streamlit/secrets.toml` or local credentials.
- The app fetches public market data from AKShare and upstream public data providers.
- Treat exported trade logs and portfolio inputs as private financial information.
