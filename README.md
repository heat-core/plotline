# Plotline 🎬🍿

<p align="center">
  <a href="README.md"><strong>English</strong></a> &nbsp;|&nbsp; <a href="README.fa.md"><strong>فارسی</strong></a>
</p>

<p align="center">
  <strong>The Private, Offline-First TV, Anime & Movie Tracker with Exact Binge-Time Calculation</strong><br>
  <em>The definitive self-hosted, open-source alternative born from TV Time's shutdown.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/Release-v1.1.0-brightgreen.svg" alt="Release v1.1.0">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white" alt="Docker Ready">
  <img src="https://img.shields.io/badge/Self--Hosted-100%25-green.svg" alt="100% Self-Hosted">
  <img src="https://img.shields.io/badge/Offline--First-Zero_Cloud-orange.svg" alt="Offline-First">
</p>

---

## 📖 Table of Contents
- [Why Plotline?](#-why-plotline)
- [Key Features](#-key-features)
- [Quick Start](#-quick-start)
  - [Windows (1-Click)](#1-windows-one-click)
  - [Linux / macOS / Terminal](#2-linux--macos--terminal)
  - [Docker & Docker Compose](#3-docker--self-hosting)
  - [Mobile App (PWA)](#4-mobile-app-pwa-for-ios--android)
  - [Standalone Desktop Executable](#5-building-standalone-desktop-app)
- [Multi-Platform Migration](#-migration-hub)
- [Jellyfin & Plex Scrobbling](#-media-server-scrobbler)
- [Releases & Packages](#-releases--packages)
- [License](#-license)

---

## 💡 Why Plotline?

For over a decade, millions of people tracked every television show, anime episode, and movie they watched on TV Time. Then services shut down, databases get wiped, and decades of personal memories, check-ins, and binge stats disappear into thin air.

I extracted my personal database directly from my phone's local cache right before the lights went out. That experience proved one fundamental truth:

> **Your personal media history belongs on your own machine — not locked inside a fragile, ad-bloated third-party cloud.**

**Plotline** is built from scratch to be the permanent home for your watch history. It runs locally on your PC or home server, operates 100% offline with zero cloud telemetry, requires no accounts or subscriptions, and features the exact mathematical binge-time engine made famous by TV Time.

---

## ✨ Key Features

### 👥 1. Multi-Profile Engine (Netflix-Style Family Profiles)
- Create and switch between multiple user profiles in one click (`Dororo 👑`, `Sarah 🍿`, `Kids 🎮`).
- Each profile maintains completely isolated watch history, episode ticks, rewatch multipliers, notes, and achievement badges.
- Base show and movie metadata is shared — zero duplicate disk space or redundant API downloads.

### ⏱️ 2. Exact Binge-Time Engine (Per-Tab Banners)
- **Series Binge Banner**: Dedicated time breakdown for TV shows and anime (Months, Days, Hours, Minutes).
- **Movies Binge Banner**: Dedicated time breakdown for cinema releases.
- **Combined Master Banner**: Full lifetime binge analytics on the Stats tab.
- **Clean "To Watch" Shelf**: Your unwatched next-episode feed stays clean with zero banner clutter.

### 🔍 3. Unified TV, Movie & Anime Metadata (Jikan / MyAnimeList)
- 1-click search powered by TVMaze, TMDB, and **Jikan API v4 (MyAnimeList)**.
- Anime series and movies are seamlessly integrated into your library without clumsy separate tabs.
- Pulls official season episode lists, air dates, overviews, networks, runtimes, and high-res posters automatically.

### 📅 4. Smart Future Air Schedule & Time Sync
- Strictly filters upcoming releases (`air_date >= date('now')`) with live countdowns.
- Automatic transition: once an episode airs, it moves automatically to your **To Watch** queue.
- Live time synchronization with network NTP servers, featuring seamless offline fallback to your system hardware clock.

### 💾 5. Offline Media Storage with Size Preview
- **Stream Mode (0 MB Disk)**: Stream artwork directly from CDN servers without eating up local drive space.
- **Full Offline Mode**: Download and cache all posters to disk with estimated download size preview (e.g. `~3.6 MB for 20 titles`).

### 🏆 6. Achievement Badges & "Plotline Wrapped"
- Unlock custom milestones as you log episodes, movies, anime, and rewatches.
- Generate high-res infographic cards (Plotline Wrapped canvas PNG) ready for social sharing.

### 📡 7. Jellyfin & Plex Media Server Scrobbling
- Built-in webhook endpoint (`/api/scrobble/webhook`).
- Automatically checks off episodes and movies the moment playback completes on your home server.

### 🌐 8. Native Bilingual Interface (English LTR & Persian RTL)
- Default original language is English (LTR).
- One-click instant switch to complete Persian (فارسی RTL) with localized numerals and typography.

---

## 🚀 Quick Start

### 1. Windows (One-Click)
1. Download or clone this repository.
2. Double-click `run_app.bat`.
3. Plotline starts its server and opens `http://localhost:8765` in your default browser.

### 2. Linux / macOS / Terminal
Plotline relies purely on standard Python 3.10+ without any bloated external packages:
```bash
git clone https://github.com/heat-core/plotline.git
cd plotline
python server.py
```
Open `http://localhost:8765` in your browser.

### 3. Docker & Self-Hosting
Run Plotline on your home server, NAS (Synology, TrueNAS, Unraid), or Raspberry Pi:
```bash
docker compose up -d
```
All database records and cached posters persist safely in `./data/`.

### 4. Mobile App (PWA for iOS & Android)
Plotline is an installable Progressive Web App:
1. Open `http://<your-server-ip>:8765` on your phone (Safari on iOS, Chrome on Android).
2. Tap **Share** (iOS) or **Options** (Android) and choose **Add to Home Screen**.
3. Plotline launches as a full-screen standalone application with offline support.

### 5. Building Standalone Desktop App
Want a single `.exe` file with zero Python prerequisites?
```bash
pip install pyinstaller
python build_desktop.py
```
Your standalone executable will be packaged directly into `dist/Plotline/Plotline.exe`.

---

## 🔄 Migration Hub

Moving from another tracker? Plotline includes 1-click importers:
- **TV Time**: Import from iOS `.imazingapp` container, raw SQLite cache, or JSON export.
- **Letterboxd**: Upload your `watched.csv` export.
- **Trakt.tv**: Import your full watch history JSON.

---

## 📡 Media Server Scrobbler

To automatically track playback from your home media server:
- **Jellyfin**: In Dashboard > Plugins > Webhook, add a generic webhook pointing to `http://<plotline-ip>:8765/api/scrobble/webhook` on **Playback Stop**.
- **Plex**: In Settings > Webhooks, add `http://<plotline-ip>:8765/api/scrobble/webhook`.

---

## 📦 Releases & Packages

- **GitHub Releases**: Download pre-compiled standalone binaries and release archives from the [Releases](https://github.com/heat-core/plotline/releases) page.
- **Container Packages**: Pull official multi-architecture Docker container from GitHub Container Registry (`ghcr.io/heat-core/plotline:latest`).

---

## 📄 License

Plotline is free, open-source software licensed under the [MIT License](LICENSE).
Built with love for media preservation and data sovereignty.
