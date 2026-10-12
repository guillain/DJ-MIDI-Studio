# 🐞 Report a Problem

> Something went wrong? `Help → Report a Problem…` prepares a bug report
> with the details that help fix it, lets you read and edit every word, then
> opens it as a pre-filled GitHub issue.

📍 [Docs](../../README.md) › [End user](../README.md) › [Features](README.md) › Report a Problem

## Table of Contents

- [Send a report](#send-a-report)
- [What the report contains](#what-the-report-contains)
- [What it never contains](#what-it-never-contains)
- [Long reports](#long-reports)
- [Related](#related)

## Send a report

1. Choose `Help → Report a Problem…`.
2. Give the report a short title, and describe what happened under
   **What happened** — what you did, what you expected, what you got.
3. Read the rest of the text. Change or delete anything you'd rather not
   share.
4. Click **Copy & Open GitHub**. The text goes to your clipboard and your
   browser opens a new issue on the project's GitHub page, already filled
   in. Check it once more and submit it there (you need a GitHub account).

The app itself sends nothing: the report only leaves your computer when you
submit the issue in your browser. `Cancel` throws it away.

## What the report contains

- The DJ MIDI Studio version.
- Your system (for example `macOS 15.1 (arm64)`), and the Python and Qt
  versions the app runs on.
- The controllers and DJ software enabled in ⚙ Preferences → Plugins.
- The last 40 lines of the app's execution log (what it did and any
  errors), set up in [⚙ Preferences → General](workspace.md).

## What it never contains

- Nothing from your mappings or your music library: no mapping content, no
  track list, no tags.
- No user name in file paths: a path in your home folder is shortened to
  `~` (`~/Music/set.xml`), and so is any other user's home folder that
  shows up in the log.

Log lines can still name a file you opened (in that shortened form). If a
name is private, delete that line before you click **Copy & Open GitHub**.

## Long reports

A web link can only carry so much text. When the report is too long, the
issue opens with everything except the log lines, and a note where they
go: paste the clipboard there — it holds the full report, exactly as you
edited it.

## Related

- [Workspace and preferences](workspace.md)
- [User guide](../user-guide.md)
