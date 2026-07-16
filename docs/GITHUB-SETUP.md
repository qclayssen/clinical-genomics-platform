# Pushing this repo to GitHub

The project is a normal git repo with commits already under your identity
(`qclayssen <quentin.clayssen@gmail.com>`). It just needs a GitHub remote and a push.

The **auth step must be done by you** — creating a repo and authenticating require your
GitHub credentials, which an assistant can't (and shouldn't) handle. It's two commands.

## One-time setup

```bash
# 1. Log in to GitHub (opens a browser; pick GitHub.com → HTTPS → login with browser)
gh auth login

# 2. Create the PRIVATE repo and push everything
./scripts/push_to_github.sh
```

That's it. The script renames the branch to `main`, creates
`clinical-genomics-platform` as a **private** repo, wires up `origin`, and pushes.

## Everyday use afterwards

Normal git — commit as you work, push when you want:

```bash
git add -A
git commit -m "…"
git push
```

## Notes

- **Private by default.** To make it public later: `gh repo edit --visibility public`
  (or flip `VISIBILITY` in `scripts/push_to_github.sh` before the first run).
- **Custom name:** `./scripts/push_to_github.sh my-other-name`
- **Prefer SSH?** Your key exists locally but GitHub rejected it in testing
  (`Permission denied (publickey)`) — add it at github.com → Settings → SSH keys, or just
  use the `gh` HTTPS flow above, which is simpler.
- Nothing here is auto-pushed. You stay in control of what goes public and when.

## Social preview image

When the repo link is shared on LinkedIn, Twitter, or Slack, GitHub shows a social preview
card. By default it's just the repo name on a plain background.

To set a custom banner (1280 x 640 px recommended):

1. Create or export a banner image — e.g. the architecture diagram or a styled project title.
   Save it to `docs/assets/social-preview.png`.
2. Go to your repo on GitHub → **Settings** → **General** → scroll to **Social preview**.
3. Upload the image.

A good social preview shows the project name, a one-line tagline, and a hint of the
tech stack (DNA helix + AWS + dashboard). Tools like Figma, Canva, or even Excalidraw
work well for this.
