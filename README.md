# tox-shelf

package manager for touchdesigner. `shelf install` any .tox on github and it shows up in your palette.

```
shelf install wintd
shelf install raganmd/touchdesigner-save-external
shelf install dotsimulate/TDFam@^1
```

## install

windows, paste into powershell:

```
irm https://raw.githubusercontent.com/intrapersonal/tox-shelf/main/install.ps1 | iex
```

that drops `shelf.exe` into `%LOCALAPPDATA%\tox-shelf\bin` and puts it on your PATH. open a new terminal after.

if you'd rather use python (3.9+, mac works too):

```
pip install git+https://github.com/intrapersonal/tox-shelf
```

## using it

```
shelf search depth                    the shelf index + github
shelf install wintd                   a short name from the index
shelf install someone/repo            any public repo with .tox files in it
shelf install someone/repo@^1.2       newest version that matches
shelf install someone/repo#dev        a branch, tag or commit
shelf install https://github.com/someone/repo/tree/main/components/blur
shelf install https://example.com/thing.tox
shelf install ./my-folder
shelf info someone/repo               look before you install, shows versions
shelf ls
shelf update
shelf rm wintd
shelf where wintd                     path to the tox
```

everything lands in `%LOCALAPPDATA%\tox-shelf\packages` and gets copied into your palette under **My Components > shelf**. if td is already open, right click that folder and hit **Refresh Folder**.

repos with version tags (`v1.2.0`, `1.2.0`, even `ver.1.2`) install the newest tag. repos without tags install the latest commit, shown like `main@3fa9c21`.

## inside touchdesigner

```
shelf td
```

it copies a line for you. in td hit alt+t for the textport, paste it, enter. you get a **shelf** COMP in whatever network you're looking at, and it saves `shelf.tox` into your palette so next time you just drag it in.

on the **Shelf** page:

- **Package**: same stuff you'd type after `shelf install`
- **Install**: installs it, and places it in your network if **Place After Install** is on
- **Install To**: everywhere (palette) or just this project
- **Installed** + **Place In Network**: drop anything you've got into the network you're looking at
- **Remove**, **Update All**, **Refresh**
- **Search** + **Go**: results show up under **Results**, pick one and hit Install

it runs shelf in the background, so td doesn't freeze while stuff downloads. if it can't find shelf, set **Shelf Exe** on the Setup page.

## per project

for when you want a project to carry its own components, like npm:

```
cd my-td-project
shelf init
shelf add intrapersonal/wintd
```

that writes `shelf.json` and `shelf.lock` and puts the files in `shelf_modules/`. commit `shelf.json` and `shelf.lock`, then whoever clones it runs `shelf sync` and gets the exact same versions. `shelf drop` takes something out, `shelf update` bumps everything.

in td set **Install To** to **This Project** and placed COMPs get their external tox pointed at `shelf_modules/...` with a relative path, so the project still opens on someone else's machine.

## making your stuff installable

any public repo with .tox files already works. without a shelf.json it grabs everything in a `release/` folder if there is one, otherwise every .tox except the ones in folders like `dev`, `examples`, `test` or `Backup`.

to control it yourself, run `shelf init` in your repo or write a `shelf.json`:

```json
{
  "name": "my-thing",
  "version": "1.0.0",
  "description": "what it does",
  "tox": ["release/my-thing.tox"],
  "include": ["docs/*.md"],
  "touchdesigner": "2023.11000",
  "dependencies": {
    "intrapersonal/wintd": "*"
  }
}
```

- `tox` is what goes in the palette, `include` is anything else that should come along
- `touchdesigner` is the oldest build it works on, people on older builds get a warning
- `dependencies` get installed with it. values are ranges like `^1.0`, or `#main` for a branch
- `shelf check` tells you if something's off before you push
- tag releases like `v1.0.0` so people can pin versions

want a short name like `shelf install my-thing`? open a PR adding it to [`toxshelf/index.json`](toxshelf/index.json). the `touchdesigner` topic on your repo helps `shelf search` find it too.

## other stuff

- `--json` on any command for machine readable output (that's how the td side talks to it)
- `shelf doctor` checks your setup
- `shelf palette` shows where the palette is. `shelf palette set <folder>` if yours lives somewhere else, `shelf palette off` to stop copying into it
- search uses the github api, which allows 60 searches an hour. if you hit that, `shelf config set token <github token>`
- installing doesn't touch the api at all, so it doesn't count against that
- if downloads get blocked on your network it falls back to git if you have it
- zero dependencies, just python's standard library

## license

MIT

made by mason arcieri
