# AI Documentation Manifest

This document describes the comprehensive AI-ready documentation suite created for CodeVault.

## Purpose

This documentation is specifically designed for AI assistants (Claude, GPT-4, Copilot, etc.) to understand and navigate the CodeVault codebase. Each document serves a specific purpose in the knowledge hierarchy.

## File Locations and Contents

### Root Level

#### CLAUDE.md (214 lines)
**Purpose:** Primary AI context document
**Audience:** Any AI assistant beginning work on CodeVault

**Contains:**
- Complete project overview and use cases
- Full technology stack breakdown
- Architecture diagram with data flow
- Exhaustive directory structure (all 17 top-level components)
- Key design decisions (5 fundamental patterns)
- Important coding patterns (how to add new tools, parsers, endpoints)
- Common development commands
- All critical environment variables
- Neo4j graph schema (node types, relationships)
- Coding conventions and best practices

**Why it's important:** This is a one-stop reference that teaches an AI the entire system architecture and conventions before diving into code.

#### README.md (enhanced)
**Purpose:** Human-readable project overview + quick start
**Audience:** Developers, DevOps, users

**Updates made:**
- Clarified description: now mentions all 5 supported languages
- Added "Supported Languages" table with entity extraction details
- Added "Quick Start (60 seconds)" section linking to automation scripts
- Preserved all existing API reference, MCP setup, and configuration documentation

## Documentation Directory (docs/)

### ARCHITECTURE.md (79 lines)
**Purpose:** Deep dive into system design
**Audience:** AI assistants designing new features or debugging complex interactions

**Contains:**
- Three-stage pipeline explanation (Parsing → Indexing → Querying)
- Data flow diagram from source code to query results
- MCP integration architecture
- Transport layers (stdio vs HTTP+SSE)
- Security model (JWT, API tokens, RBAC, rate limiting)
- Scaling considerations (indexing strategies, concurrency, caching)

**Key insight:** Shows how all components work together end-to-end.

### MCP_SETUP.md (123 lines)
**Purpose:** Complete guide to connecting CodeVault to AI tools
**Audience:** Users setting up MCP connections, AI assistants helping with configuration

**Contains:**
- Step-by-step Claude Desktop setup (3 parts + test)
- Cursor setup (2 options: SSE and stdio)
- Generic MCP client setup (Windsurf, Continue.dev, etc.)
- All 11 available MCP tools with descriptions
- Common troubleshooting scenarios with solutions

**Why separate:** MCP is the primary interface between AI agents and CodeVault, so it deserves dedicated, focused documentation.

### AI_DOCUMENTATION_MANIFEST.md (this file)
**Purpose:** Index and guide to the entire documentation suite
**Audience:** AI assistants or humans wanting to understand what's documented where

## Scripts Directory (scripts/)

### setup.sh (41 lines, executable)
**Purpose:** One-command Docker Compose initialization
**Audience:** DevOps, developers setting up local environment

**Automation:**
- Validates Python 3 and Docker prerequisites
- Creates .env from template
- Auto-generates cryptographically secure SECRET_KEY
- Starts all 5+ Docker services (PostgreSQL, Redis, Neo4j, Django, Celery, Celery Beat)
- Waits 10 seconds for service health
- Runs Django migrations automatically
- Displays all dashboard URLs and next steps

**Result:** From zero to running system in ~15 seconds (after Docker pull).

### mcp_quickstart.sh (48 lines, executable)
**Purpose:** Automated end-to-end MCP onboarding
**Audience:** Users wanting to connect CodeVault to Claude Desktop

**Automation (4 arguments):**
1. Email address (for registration)
2. Password (for user account)
3. Project name (what to call the indexed codebase)
4. Code path (local filesystem path to code to index)

**Steps:**
- Registers user (idempotent)
- Logs in and gets JWT
- Creates project in CodeVault
- Triggers full ingestion with `--sync --clear` (indexes all files)
- Creates long-lived API token
- Outputs ready-to-paste Claude Desktop configuration

**Result:** User has MCP connection ready in ~60-120 seconds depending on codebase size.

## How AI Assistants Should Use This Documentation

### Initial Context Loading (Before Code Analysis)
1. Read **CLAUDE.md** completely to understand the system
2. Skim **ARCHITECTURE.md** to understand data flow
3. Reference **MCP_SETUP.md** if helping with MCP configuration

### During Development
- Check **CLAUDE.md** section "Important Patterns" when adding features
- Reference specific command formats from CLAUDE.md "Common Commands"
- Use ARCHITECTURE.md to understand how components interact

### When Debugging
- Check "Security Model" in ARCHITECTURE.md for auth issues
- Consult "Coding Conventions" in CLAUDE.md for style violations
- Reference "Troubleshooting" in MCP_SETUP.md for connection issues

## Documentation Completeness Checklist

- [x] Project overview and vision
- [x] Complete technology stack
- [x] Architecture diagrams with data flow
- [x] Directory structure with component descriptions
- [x] Design decisions and rationale
- [x] Patterns for common extensions (new tools, parsers, endpoints)
- [x] Environment configuration reference
- [x] Authentication and security model
- [x] Database schema (Neo4j)
- [x] Coding conventions and standards
- [x] MCP tool reference
- [x] Setup automation scripts
- [x] Troubleshooting guides
- [x] Multi-language support documentation
- [x] API reference (in README.md, preserved)

## Key Features of This Documentation Suite

**AI-First Design:** Every document is written to be parseable and actionable by language models, with clear structure, code blocks, and explicit cross-references.

**Self-Contained:** CLAUDE.md + ARCHITECTURE.md provide complete system understanding without external references.

**Actionable:** Scripts automate 90% of setup complexity; documentation explains the 10% that requires human decisions.

**Multi-Language:** Covers Python, JavaScript/TypeScript, Go, Rust, and Java with specific entity extraction details.

**Enterprise-Ready:** Documents security model, RBAC, rate limiting, scaling considerations, and production patterns.

**Evergreen:** Uses technology-agnostic descriptions where possible, with specific version numbers only where necessary.

## Maintenance Guidelines

When updating the codebase:

1. **New MCP tool?** Update CLAUDE.md "Important Patterns" section + MCP_SETUP.md tool table
2. **New language parser?** Update README.md language table + CLAUDE.md directory structure
3. **New authentication method?** Update CLAUDE.md "API Authentication" section
4. **New command?** Add to CLAUDE.md "Common Commands" section
5. **Architecture change?** Update ARCHITECTURE.md data flow diagram

All documentation should be updated before or alongside code changes, not after.
