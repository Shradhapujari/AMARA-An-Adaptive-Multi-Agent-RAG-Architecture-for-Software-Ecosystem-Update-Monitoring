# Wiki source

These files are the source of the GitHub wiki at
<https://github.com/Shradhapujari/Adaptive-Multi-Agent-RAG-Architecture-for-Software-Ecosystem-Update-Monitoring/wiki>.

They live in the main repository so wiki edits are reviewable in a pull request
alongside the code they describe. The wiki itself is a separate git repository
(`<repo>.wiki.git`) that GitHub creates only after the first page is saved
through the web UI.

## Publishing

One-time, in the browser: open the repository's **Wiki** tab and save any page
(the default "Home" is fine — it will be overwritten). That creates the wiki
repository.

Then, from the repository root:

```bash
git clone https://github.com/Shradhapujari/Adaptive-Multi-Agent-RAG-Architecture-for-Software-Ecosystem-Update-Monitoring.wiki.git /tmp/marag-wiki
cp wiki/*.md /tmp/marag-wiki/
rm -f /tmp/marag-wiki/README.md          # this file is not a wiki page
cd /tmp/marag-wiki
git add -A && git commit -m "docs: sync wiki from repo" && git push
```

`_Sidebar.md` is rendered by GitHub as the wiki's navigation panel; it is not a
page of its own. Page names come from filenames, so a link like
`[Architecture](Architecture)` resolves to `Architecture.md`.
