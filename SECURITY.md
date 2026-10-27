# Security Policy

## Supported Versions

Only the latest release and the current `main` branch receive security fixes.

| Version        | Supported          |
| -------------- | ------------------ |
| Latest release | :white_check_mark: |
| Older releases | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability or critical defect in LTC AutoClicker, please report it responsibly:

1. **Do not create a public issue**.
2. Use GitHub's private vulnerability reporting feature on the repository (under the **Security** tab).
3. Alternatively, contact the maintainers directly through their GitHub profile.

Please provide:
- A clear description of the vulnerability and potential impact.
- Exact reproduction steps or a minimal proof of concept.

### Privacy Notice: Error Reports
LTC AutoClicker does not write crash logs to disk. If an unexpected error occurs, it shows an on-screen error dialog with your user folder path replaced by `%USERPROFILE%`. Check the text before sharing a screenshot of it publicly.

The v1.0.0 release and earlier builds wrote crash logs to `%LOCALAPPDATA%\AutoClicker-LTC\crash_reports\`. Those files can contain your Windows username in file paths, so redact them before sharing. The folder is safe to delete.
