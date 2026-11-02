# Changelog

All notable changes to Velox. Versions follow [semantic versioning](https://semver.org/):
**major** for big changes, **minor** for new features, **patch** for fixes.

## 5.2.1

**Fixed**
- The on-screen display (speed, skip, volume) stayed invisible on pages that switch all animations off, such as Verbatim and Sequo when your system asks for less motion

## 5.2.0

**New**
- Velox also works on the recordings in Verbatim on your own laptop (127.0.0.1:7861): shortcuts, speed and the on-screen display. Other pages on your laptop are left alone
- Your browser asks once for permission to run on pages on your own laptop

## 5.1.0

**New**
- Recordings with slides and webcam as two pictures: Velox now always downloads the slides, no longer sometimes only the webcam
- With downloads to Verbatim on, the webcam is saved too, and Verbatim puts both side by side in one video

## 5.0.0

**Changed**
- Velox now uses its own name everywhere: add-on id, files, settings and the update address
- This is a new add-on for Firefox and Zen: remove the old version, then install this one. Settings and the link with Sequo start fresh

## 4.5.0

**New**
- With downloads to Verbatim on, PDF and PPTX files on Toledo get a button that saves them to the course folder

## 4.4.1

- Links to report a problem, the source code and the privacy policy now point to the Trivium repository.

## 4.4.0

**Changed**
- SwiftSkip is now called **Velox**, part of Trivium, with Sequo (formerly Inhaal) and Verbatim
- A new logo in the same blue as the other two apps
- Menu, settings and welcome page use exactly the same styling as Sequo
- The settings page opens one section at a time
- The overlays on the player are one calm dark, in the same shapes as Sequo

**New**
- Appearance: choose system, light or dark for the menu and settings

## 4.3.0

**Changed**
- A calmer new look, the same as Inhaal: popup, settings page and the overlays on the player
- Settings are one click away: a button at the top of the menu, and in the shortcut overview (`?`) on the player
- The settings page is grouped, with a list of sections on wide screens

## 4.2.0

**New**
- **Downloads to Verbatim** (optional): recordings go to `Downloads/Verbatim/<course code>/`, where Verbatim picks them up

## 4.1.2

**Changed**
- Link with Inhaal: a lecture recorded in parts is ticked off when the parts together cover most of it, not after the first part

## 4.1.1

**Fixed**
- Link with Inhaal: recordings without a lecture title in Toledo now reach Inhaal too

## 4.1.0

**New**
- **Link with Inhaal** (optional): lectures you watched are ticked off by themselves, and your position and downloads show up in Inhaal. Off until you link it from Inhaal's settings

## 4.0.2

**Changed**
- Firefox / Zen: updates now come from a new address, so future versions keep arriving by themselves

## 4.0.1

**Fixed**
- Chrome: downloads kept their full name (course – lecture – date), and the menu kept showing the lecture, after the lecture had been open for a while
- A player that switches to another lecture without reloading now downloads and resumes that lecture, not the first one
- Much less work in the background on big Toledo pages, and none in hidden tabs
- Play/pause no longer risks pressing another player button (like *Replay*)

## 4.0.0

A complete rework: one codebase for every browser, a new look, and many new features.

**New**
- Downloads are saved as **`.mp4`** with a clear name (course – lecture – date), download faster (4 parts at a time) and retry by themselves when a part fails
- **Continue where you left off** when you reopen a lecture, with a *Start over* button
- **Remembers your playback speed**; speed steps of 0.25× (or 0.1×) from 0.25× to 4×
- Press **`?`** to see every shortcut over the video
- **All shortcuts can be changed**, up to two keys per action, also with Shift/Ctrl/Alt
- Shortcuts work **without clicking in the player first**
- **AZERTY**: `^` / `$` change the speed and the number row works without Shift
- **Dutch and English**, following your browser or chosen in the settings
- New **settings page**, **welcome page**, and a minimal **menu** (lecture + download, speed, skip interval)
- Works on **other sites** you enable yourself (e.g. Kaltura at another school)
- **Firefox / Zen: automatic updates**

**Improved**
- Redesigned player controls: a collapsible **Download** button with a progress ring, one consistent style, light/dark menus
- Skipping back at the start (or forward at the end) no longer counts up −10, −20, −30 …
- SwiftSkip only asks access to Toledo, KU Leuven and Kaltura instead of every website
- After an update, open lectures keep working without a reload
- Keyboard and screen-reader friendly menus

## 3.2

The original Firefox and Chrome versions.
