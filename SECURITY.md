# Security Policy

## Supported Versions

Only the latest active version on `master` / `main` receives security patches and updates.

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| 1.x     | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability or critical defect in LTC AutoClicker, please report it responsibly:

1. **Do not create a public issue**.
2. Use GitHub's private vulnerability reporting feature on the repository (under the **Security** tab).
3. Alternatively, contact the maintainers directly through their GitHub profile.

Please provide:
- A clear description of the vulnerability and potential impact.
- Exact reproduction steps or a minimal proof of concept.

### Privacy Notice: Crash Reports
LTC AutoClicker logs diagnostic stack traces locally to `%LOCALAPPDATA%\AutoClicker-LTC\crash_reports\` when an unhandled exception or crash occurs. These log files can include local file system paths containing your Windows username (e.g., `C:\Users\<username>\...`). 

**Please redact or sanitize your username from crash reports before sharing them publicly.**
