"""Main window — 3-panel layout: file tree | editor | AI panel."""

import difflib
import logging
import os

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QTreeView, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QLabel, QLineEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFileSystemModel, QKeySequence, QShortcut

from harness.audio_settings import AudioSettingsStore
from harness import audio_devices
from ui.editor_panel import EditorPanel
from ui.ai_panel import AiPanel
from harness.tts_navigator import TtsNavigator

log = logging.getLogger(__name__)

# Guard: skip files bigger than 1 MB (Monaco struggles with huge files too).
_MAX_FILE_SIZE = 1_048_576


class DiffPanel(QWidget):
    """Inline diff display with Accept / Reject buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path = None
        self._modified_content = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        self._header = QLabel("Proposed changes")
        self._header.setStyleSheet(
            "color:#dcdcaa; font-weight:bold; font-size:12px;"
            " font-family:Consolas,monospace;"
        )
        layout.addWidget(self._header)

        # Diff view
        self._diff_view = QPlainTextEdit()
        self._diff_view.setReadOnly(True)
        self._diff_view.setFont(QFont("Consolas", 11))
        self._diff_view.setStyleSheet(
            "QPlainTextEdit { background:#1e1e1e; color:#d4d4d4; border:1px solid #3c3c3c; }"
        )
        layout.addWidget(self._diff_view, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        self._accept_btn = QPushButton("Accept")
        self._accept_btn.setStyleSheet(
            "QPushButton { background:#388c2c; color:white; padding:6px 16px;"
            " font-weight:bold; border-radius:3px; border:none; }"
            "QPushButton:hover { background:#45a835; }"
        )
        self._reject_btn = QPushButton("Reject")
        self._reject_btn.setStyleSheet(
            "QPushButton { background:#c24038; color:white; padding:6px 16px;"
            " font-weight:bold; border-radius:3px; border:none; }"
            "QPushButton:hover { background:#d4524a; }"
        )
        btn_row.addStretch()
        btn_row.addWidget(self._accept_btn)
        btn_row.addWidget(self._reject_btn)
        layout.addLayout(btn_row)

        self.hide()

    def show_diff(self, file_path: str, original: str, modified: str):
        """Display a unified diff and store the proposal for accept/reject."""
        self._file_path = file_path
        self._modified_content = modified

        diff_lines = difflib.unified_diff(
            original.splitlines(keepends=True),
            modified.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
        )
        self._diff_view.setPlainText("".join(diff_lines))
        self._header.setText(f"Proposed changes to {os.path.basename(file_path)}")
        self.show()


def _is_binary_file(path: str) -> bool:
    """Return True if file appears to be binary (contains null bytes in first 8 KB)."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True


class MainWindow(QMainWindow):
    def __init__(self, coordinator, audio_settings=None, parent=None):
        super().__init__(parent)
        self._coordinator = coordinator
        self._audio_settings = audio_settings or AudioSettingsStore()
        self.setWindowTitle("Voice Harness")
        self.resize(1400, 850)
        self.setStyleSheet("QMainWindow { background:#1e1e1e; }")

        # --- File tree (left) ---
        self._fs_model = QFileSystemModel()
        self._fs_model.setReadOnly(True)
        self._file_tree = QTreeView()
        self._file_tree.setModel(self._fs_model)
        self._file_tree.setHeaderHidden(True)
        # Hide Size, Type, Date columns — keep only Name.
        for col in (1, 2, 3):
            self._file_tree.hideColumn(col)
        self._file_tree.setStyleSheet(
            "QTreeView { background:#252526; color:#cccccc; border:none;"
            " font-family:Consolas; font-size:12px; }"
            "QTreeView::item:selected { background:#094771; }"
        )
        self._file_tree.doubleClicked.connect(self._on_file_double_click)

        # --- Editor (centre) ---
        self._editor = EditorPanel()

        # --- AI panel (right) ---
        self._ai_panel = AiPanel()

        # --- Diff panel (hidden by default, shown inline when edits arrive) ---
        self._diff_panel = DiffPanel(self)
        self._diff_panel.hide()
        self._pending_proposal = None

        # --- Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._file_tree)
        splitter.addWidget(self._editor)
        splitter.addWidget(self._diff_panel)
        splitter.addWidget(self._ai_panel)
        splitter.setSizes([220, 640, 360, 380])
        splitter.setStyleSheet("QSplitter::handle { background:#3c3c3c; width:2px; }")
        self.setCentralWidget(splitter)

        # --- Wire coordinator signals → UI ---
        coordinator.state_changed.connect(self._ai_panel.set_state)
        coordinator.recording_active_changed.connect(self._ai_panel.set_recording_active)
        coordinator.audio_level_changed.connect(self._ai_panel.set_audio_level)
        coordinator.transcription_ready.connect(self._ai_panel.populate_query)
        coordinator.llm_response_ready.connect(self._ai_panel.append_response)
        coordinator.error_occurred.connect(self._on_error_occurred)
        coordinator.edits_proposed.connect(self._on_edits_proposed)
        coordinator.edits_applied.connect(
            lambda path: self.statusBar().showMessage(
                f"Edits applied to {os.path.basename(path)}", 5000
            )
        )

        # --- Wire UI → coordinator ---
        self._ai_panel.text_submitted.connect(self._on_manual_query)
        self._ai_panel.auto_submit_requested.connect(self._on_manual_query)
        self._ai_panel.pause_toggled.connect(self._on_pause_toggle)
        self._ai_panel.ptt_pressed.connect(coordinator.ptt_press)
        self._ai_panel.ptt_released.connect(coordinator.ptt_release)
        self._ai_panel.input_device_changed.connect(self._on_input_device_changed)
        self._ai_panel.output_device_changed.connect(self._on_output_device_changed)
        self._ai_panel.wake_word_toggled.connect(self._on_wake_word_toggled)
        self._ai_panel.api_key_changed.connect(self._on_api_key_changed)
        self._ai_panel.download_models_requested.connect(coordinator.download_missing_models)
        coordinator.model_status_changed.connect(self._on_model_status_changed)
        coordinator.model_progress.connect(self._ai_panel.set_model_progress)
        coordinator.model_progress_done.connect(self._ai_panel.clear_model_progress)
        coordinator.repo_map_status_changed.connect(self._on_repo_map_status_changed)

        # --- Sync editor content to coordinator on text change ---
        self._editor.content_changed.connect(self._sync_editor_context)

        # --- TTS Navigator (Phase 4) ---
        self._tts_nav = TtsNavigator()
        coordinator.tts_chunks_ready.connect(self._on_tts_chunks_ready)
        coordinator.tts_chunk_ready.connect(self._on_tts_chunk_incremental)
        self._tts_nav.chunk_changed.connect(self._on_tts_chunk_changed)
        self._tts_nav.playback_error.connect(self._on_tts_playback_error)
        self._tts_nav.playback_finished.connect(self._on_tts_playback_finished)
        self._tts_nav.speed_changed.connect(self._ai_panel.update_speed_display)
        self._tts_nav.word_highlight.connect(self._ai_panel.highlight_word)

        # Wire AI panel TTS buttons → playback policy handlers
        self._ai_panel.tts_play_requested.connect(self._on_tts_play_requested)
        self._ai_panel.tts_stop_requested.connect(self._on_tts_stop_requested)
        self._ai_panel.tts_prev_requested.connect(self._tts_nav.prev)
        self._ai_panel.tts_next_requested.connect(self._tts_nav.next)
        self._ai_panel.tts_speed_change_requested.connect(self._on_tts_speed_change)

        # --- TTS keyboard shortcuts ---
        ctx = Qt.ShortcutContext.WindowShortcut
        QShortcut(QKeySequence(Qt.Key.Key_Right), self,
                  context=ctx).activated.connect(self._on_tts_right)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self,
                  context=ctx).activated.connect(self._on_tts_left)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self,
                  context=ctx).activated.connect(self._on_tts_space)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self,
                  context=ctx).activated.connect(self._on_tts_escape)

        self._initialize_audio_settings()

        # Push initial model-status snapshot to the UI.
        coordinator.refresh_model_status()
        # If anything is missing, kick off the download in the background.
        try:
            from harness import model_manager as _mm
            if not (_mm.whisper_present() and _mm.kokoro_present()):
                coordinator.download_missing_models()
        except (OSError, RuntimeError, ImportError) as exc:
            log.warning("Initial model presence check failed: %s", exc)

    # ------------------------------------------------------------------
    # File tree
    # ------------------------------------------------------------------
    def set_root_path(self, path: str):
        """Set the file tree root to a project directory."""
        root_idx = self._fs_model.setRootPath(path)
        self._file_tree.setRootIndex(root_idx)

    def _on_file_double_click(self, index):
        path = self._fs_model.filePath(index)
        if self._fs_model.isDir(index):
            return
        self._load_file_by_path(path)

    def _load_file_by_path(self, path: str):
        """Load a text file into the editor and update coordinator context.

        Shows a status bar message when a file is skipped or unreadable.
        """
        try:
            size = os.path.getsize(path)
        except OSError:
            self.statusBar().showMessage(f"Cannot read: {path}", 5000)
            return
        if size > _MAX_FILE_SIZE:
            self.statusBar().showMessage(
                f"File too large ({size:,} bytes, max {_MAX_FILE_SIZE:,}): {path}", 5000
            )
            return
        if _is_binary_file(path):
            self.statusBar().showMessage(f"Binary file skipped: {path}", 5000)
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            self.statusBar().showMessage(f"Cannot read: {path}", 5000)
            return
        self._editor.set_file(path, content)
        self._coordinator.set_file_context(path, content)

    # ------------------------------------------------------------------
    # Manual query
    # ------------------------------------------------------------------
    def _on_manual_query(self, text: str):
        self._ai_panel.clear_error()
        self._ai_panel.append_transcription(text)
        self._sync_editor_context()
        self._coordinator.submit_text(text)

    def _on_error_occurred(self, message: str) -> None:
        self._ai_panel.show_error(message)
        self.statusBar().showMessage(message, 8000)

    # ------------------------------------------------------------------
    # Pause / resume
    # ------------------------------------------------------------------
    def _on_pause_toggle(self, paused: bool):
        if paused:
            self._coordinator.pause_listening()
        else:
            self._coordinator.resume_listening()

    def _on_input_device_changed(self, device_index) -> None:
        self._audio_settings.set_input_device(device_index)
        self._coordinator.set_input_device(device_index)
        label = "default microphone" if device_index is None else f"microphone {device_index}"
        self.statusBar().showMessage(f"Input device set to {label}", 5000)

    def _on_output_device_changed(self, device_index) -> None:
        self._audio_settings.set_output_device(device_index)
        self._tts_nav.set_output_device(device_index)
        label = "default speakers" if device_index is None else f"speakers {device_index}"
        self.statusBar().showMessage(f"Output device set to {label}", 5000)

    def _on_wake_word_toggled(self, enabled: bool) -> None:
        self._audio_settings.set_wake_word_enabled(enabled)
        self._coordinator.set_wake_word_enabled(enabled)
        mode = "enabled" if enabled else "disabled"
        self.statusBar().showMessage(f"Wake word {mode}", 5000)

    def _on_api_key_changed(self, key: str) -> None:
        self._audio_settings.set_api_key(key)
        self._coordinator.set_api_key(key or None)
        message = "API key cleared" if not key else "API key saved"
        self.statusBar().showMessage(message, 5000)

    def _on_model_status_changed(self, summary: dict) -> None:
        self._ai_panel.set_model_status(
            whisper=bool(summary.get("whisper")),
            kokoro=bool(summary.get("kokoro")),
            api_key=bool(summary.get("api_key")),
        )

    def _on_repo_map_status_changed(self, summary: dict) -> None:
        self._ai_panel.set_repo_map_status(
            available=bool(summary.get("available")),
            chars=int(summary.get("chars", 0)),
            files=int(summary.get("files", 0)),
        )

    # ------------------------------------------------------------------
    # Keep coordinator's file context in sync with editor
    # ------------------------------------------------------------------
    def _sync_editor_context(self):
        path = self._editor.path
        content = self._editor.get_content()
        if path and path != "No file open":
            self._coordinator.set_file_context(path, content)

    # ------------------------------------------------------------------
    # Diff accept/reject flow (Phase 3a)
    # ------------------------------------------------------------------
    def _on_edits_proposed(self, proposal: dict):
        """Show the diff panel with proposed changes."""
        # Disconnect any previous handlers to prevent accumulation.
        self._disconnect_diff_buttons()

        self._pending_proposal = proposal
        self._diff_panel.show_diff(
            proposal["file_path"],
            proposal["original"],
            proposal["modified"],
        )
        self._diff_panel._accept_btn.clicked.connect(self._on_accept_edits)
        self._diff_panel._reject_btn.clicked.connect(self._on_reject_edits)

    def _disconnect_diff_buttons(self):
        """Safely disconnect diff button handlers (no-op if not connected)."""
        try:
            self._diff_panel._accept_btn.clicked.disconnect(self._on_accept_edits)
        except (TypeError, RuntimeError):
            pass
        try:
            self._diff_panel._reject_btn.clicked.disconnect(self._on_reject_edits)
        except (TypeError, RuntimeError):
            pass

    def _on_accept_edits(self):
        """Accept proposed edits — write file, update editor, git commit."""
        proposal = self._pending_proposal
        if proposal is None:
            return

        # Guard: reject stale accept if user switched to a different file.
        current_path = self._editor.path
        if current_path and current_path != "No file open":
            current_norm = os.path.normcase(os.path.normpath(current_path))
            proposal_norm = os.path.normcase(os.path.normpath(proposal["file_path"]))
            if current_norm != proposal_norm:
                self.statusBar().showMessage(
                    "Proposal rejected — active file changed since proposal", 5000
                )
                self._dismiss_diff_panel()
                return

        success = self._coordinator.accept_edits(
            proposal["file_path"], proposal["modified"]
        )
        if success:
            self._editor.set_file(proposal["file_path"], proposal["modified"])
        self._dismiss_diff_panel()

    def _on_reject_edits(self):
        """Reject proposed edits — discard and hide diff."""
        self._coordinator.reject_edits()
        self._dismiss_diff_panel()

    def _dismiss_diff_panel(self):
        """Hide diff panel and clean up handlers."""
        self._diff_panel.hide()
        self._disconnect_diff_buttons()
        self._pending_proposal = None

    # ------------------------------------------------------------------
    # TTS navigator integration (Phase 4)
    # ------------------------------------------------------------------
    def _on_tts_chunks_ready(self, chunks) -> None:
        """Load TTS chunks into navigator and start playback immediately."""
        # Phase 5: chunks already loaded incrementally via tts_chunk_ready.
        # This signal fires at the end for backward compat; only load if
        # navigator is still empty (non-streaming fallback).
        if self._tts_nav.chunk_count == 0:
            self._tts_nav.load(chunks)
        has_chunks = self._tts_nav.chunk_count > 0
        self._ai_panel.enable_tts_controls(has_chunks)
        if has_chunks and not self._tts_nav.is_playing:
            self._on_tts_play_requested()

    def _on_tts_chunk_incremental(self, sentence, wav_bytes) -> None:
        """Handle a single TTS chunk arriving from the streaming pipeline."""
        is_first = self._tts_nav.chunk_count == 0
        self._tts_nav.append_chunk(sentence, wav_bytes)
        self._ai_panel.enable_tts_controls(True)
        if is_first:
            self._on_tts_play_requested()

    def _on_tts_chunk_changed(self, index: int, sentence: str) -> None:
        """Update AI panel when navigator moves to a new chunk."""
        self._ai_panel.update_chunk_info(index, self._tts_nav.chunk_count, sentence)

    def _on_tts_playback_finished(self) -> None:
        """Called when all TTS playback is done."""
        self._coordinator.finish_tts_playback()
        self._ai_panel.enable_tts_controls(self._tts_nav.chunk_count > 0)
        self._ai_panel.clear_word_highlight()

    def _on_tts_playback_error(self, message: str) -> None:
        """Surface TTS playback failures to the visible UI."""
        self._ai_panel.append_response(f"TTS playback error: {message}")
        self.statusBar().showMessage(f"TTS playback error: {message}", 5000)

    def _on_tts_play_requested(self) -> None:
        """Start playback and transition the coordinator into speaking state."""
        if self._tts_nav.chunk_count == 0 or self._tts_nav.is_playing:
            return
        self._coordinator.begin_tts_playback()
        self._tts_nav.play_current()

    def _on_tts_stop_requested(self) -> None:
        """Stop playback and restore listening state."""
        if not self._tts_nav.is_playing:
            return
        self._tts_nav.stop()
        self._coordinator.finish_tts_playback()
        self._ai_panel.clear_word_highlight()

    def _on_tts_speed_change(self, delta: float) -> None:
        """Adjust navigator speed by delta."""
        new_speed = self._tts_nav.speed + delta
        self._tts_nav.set_speed(new_speed)

    def _on_tts_right(self) -> None:
        if self._text_widget_has_focus():
            return
        if self._tts_nav.chunk_count > 0:
            was_playing = self._tts_nav.is_playing
            if was_playing:
                self._tts_nav.stop()
            current_index = self._tts_nav.current_index
            self._tts_nav.next()
            if was_playing and self._tts_nav.current_index != current_index:
                self._on_tts_play_requested()

    def _on_tts_left(self) -> None:
        if self._text_widget_has_focus():
            return
        if self._tts_nav.chunk_count > 0:
            was_playing = self._tts_nav.is_playing
            if was_playing:
                self._tts_nav.stop()
            current_index = self._tts_nav.current_index
            self._tts_nav.prev()
            if was_playing and self._tts_nav.current_index != current_index:
                self._on_tts_play_requested()

    def _on_tts_space(self) -> None:
        if self._text_widget_has_focus():
            return
        if self._tts_nav.chunk_count > 0:
            if self._tts_nav.is_playing:
                self._on_tts_stop_requested()
            else:
                self._on_tts_play_requested()

    def _on_tts_escape(self) -> None:
        if self._text_widget_has_focus():
            return
        self._on_tts_stop_requested()

    def _text_widget_has_focus(self) -> bool:
        focus = self.focusWidget()
        if focus is None:
            return False
        if isinstance(focus, (QLineEdit, QPlainTextEdit)):
            return True
        return self._editor.isAncestorOf(focus)

    def keyPressEvent(self, event) -> None:
        """F2 acts as an in-app push-to-talk key while the main window has focus."""
        if event.key() == Qt.Key.Key_F2 and not event.isAutoRepeat():
            self._coordinator.ptt_press()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F2 and not event.isAutoRepeat():
            self._coordinator.ptt_release()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def closeEvent(self, event) -> None:
        """Shut down the editor's HTTP server on window close."""
        self._editor.shutdown()
        super().closeEvent(event)

    def _initialize_audio_settings(self) -> None:
        input_devices = audio_devices.list_input_devices()
        output_devices = audio_devices.list_output_devices()

        selected_input = self._resolve_initial_device(
            self._audio_settings.input_device(),
            input_devices,
            audio_devices.get_default_input(),
        )
        selected_output = self._resolve_initial_device(
            self._audio_settings.output_device(),
            output_devices,
            audio_devices.get_default_output(),
        )
        wake_word_enabled = self._audio_settings.wake_word_enabled()

        self._ai_panel.set_audio_devices(
            input_devices,
            output_devices,
            selected_input=selected_input,
            selected_output=selected_output,
        )
        self._ai_panel.set_wake_word_enabled(wake_word_enabled)

        self._coordinator.set_input_device(selected_input)
        self._coordinator.set_wake_word_enabled(wake_word_enabled)
        self._tts_nav.set_output_device(selected_output)

        # --- API key initialization ---
        import os
        api_key = self._audio_settings.api_key() or os.environ.get("GEMINI_API_KEY")
        if api_key:
            self._coordinator.set_api_key(api_key)
            self._ai_panel.set_api_key(api_key)

    def _resolve_initial_device(self, saved_device, devices, default_device):
        available_indices = {device["index"] for device in devices}
        if saved_device is not None and not devices:
            return saved_device
        if saved_device in available_indices:
            return saved_device
        if default_device in available_indices:
            return default_device
        return None
