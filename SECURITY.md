# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 2.0.x   | ✅ Active support   |
| 1.0.x   | ❌ No longer supported |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT open a public GitHub issue**
2. Email: **kulkarnishub377@gmail.com**
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Acknowledgement**: Within 48 hours
- **Initial Assessment**: Within 1 week
- **Fix & Disclosure**: Within 30 days (for valid reports)

## Scope

The following are in scope:
- API endpoint vulnerabilities (injection, authentication bypass)
- XSS or CSRF in the frontend
- Path traversal in file upload/download
- Information disclosure via error messages
- Container escape or privilege escalation

The following are **out of scope**:
- Denial of service on local instances
- Issues in third-party dependencies (report upstream)
- Social engineering attacks

## Security Best Practices for Users

- Run the pipeline on a trusted network — the API has no authentication by default
- Use Docker with read-only volumes for production deployments
- Keep Ollama and all dependencies updated
- Never expose the API port (8000) to the public internet without a reverse proxy
