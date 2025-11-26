import streamlit as st
import yt_dlp
import os
import re
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="YouTube Downloader", page_icon="🎥", layout="centered")
st.title("🎥 YouTube Downloader (Video, Audio, Playlists)")


# ---------------------------------------------------------
# Automatic filename cleaner
# ---------------------------------------------------------
def clean_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


# ---------------------------------------------------------
# Progress Hook
# ---------------------------------------------------------
def progress_hook(d):
    if d["status"] == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)
        if total:
            progress = downloaded / total
            st.session_state.progress_bar.progress(progress)
            speed = d.get("speed", 0)
            st.session_state.speed_text.text(f"Speed: {round(speed/1024/1024,2)} MB/s")
    elif d["status"] == "finished":
        st.session_state.progress_bar.progress(1.0)
        st.session_state.speed_text.text("Processing file…")


# ---------------------------------------------------------
# Fetch Formats
# ---------------------------------------------------------
def fetch_formats(url):
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get("formats", []):
            label = f"{f.get('format_id')} - {f.get('resolution','audio')}"

            if f.get("filesize"):
                label += f" ({round(f['filesize']/1024/1024,2)} MB)"

            formats.append((label, f.get("format_id"), f))

        return info, formats
    except Exception as e:
        st.error(f"Error fetching formats: {e}")
        return None, []


# ---------------------------------------------------------
# Threaded Playlist Download
# ---------------------------------------------------------
def download_single_video(url, fmt, output):
    ydl_opts = {
        "format": fmt,
        "outtmpl": os.path.join(output, "%(title)s.%(ext)s"),
        "windowsfilenames": True,
        "progress_hooks": [progress_hook],
        "quiet": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def download_playlist_threaded(playlist_urls, fmt, output, max_threads=4):
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        for link in playlist_urls:
            executor.submit(download_single_video, link, fmt, output)


# ---------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------
url = st.text_input("Enter YouTube Video / Playlist URL")
download_path = st.text_input("Download Folder", value="downloads")

filter_type = st.radio(
    "Type Filter",
    ["All Formats", "Video Only", "Audio Only"],
    horizontal=True
)

if url:
    st.info("Fetching available formats…")
    info, formats = fetch_formats(url)

    if info:
        st.subheader("📄 Info")
        st.write(f"**Title:** {info.get('title','N/A')}")
        st.write(f"**Type:** {'Playlist' if 'entries' in info else 'Single Video'}")

        # Filter formats
        if filter_type == "Video Only":
            formats = [(l, fid, f) for l, fid, f in formats if f.get("vcodec") != "none"]
        elif filter_type == "Audio Only":
            formats = [(l, fid, f) for l, fid, f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]

        # Format selector
        labels = [l for l, fid, f in formats]
        selected_label = st.selectbox("Choose quality:", labels)
        selected_fmt = dict((l, fid) for l, fid, _ in formats)[selected_label]

        # Initialize progress UI
        if "progress_bar" not in st.session_state:
            st.session_state.progress_bar = st.progress(0)
        if "speed_text" not in st.session_state:
            st.session_state.speed_text = st.empty()

        # Button
        if st.button("Download"):
            os.makedirs(download_path, exist_ok=True)
            st.session_state.progress_bar.progress(0)
            st.session_state.speed_text.text("Starting…")

            # Playlist
            if "entries" in info:
                st.warning("Playlist detected — downloading with multithreading...")
                playlist_urls = [e["url"] for e in info["entries"] if e]

                try:
                    download_playlist_threaded(
                        playlist_urls,
                        selected_fmt,
                        download_path,
                        max_threads=4,
                    )
                    st.success("Playlist download complete!")
                except Exception as e:
                    st.error(f"Playlist download failed: {e}")

            # Single Video
            else:
                try:
                    download_single_video(url, selected_fmt, download_path)
                    st.success("Download completed!")
                except Exception as e:
                    st.error(f"Download failed: {e}")
