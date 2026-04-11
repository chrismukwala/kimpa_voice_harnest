"""AI panel — response display + voice status + manual input + TTS controls."""

import html

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGraphicsOpacityEffect,
    QGridLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QLabel,
)
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, pyqtSignal, Qt
from PyQt6.QtGui import QFont


class AiPanel(QWidget):
    """Right-side panel: voice status, AI response log, TTS nav, and manual text input."""

    text_submitted = pyqtSignal(str)       # user typed a manual query
    pause_toggled = pyqtSignal(bool)       # True = paused, False = resumed
    tts_play_requested = pyqtSignal()
    tts_stop_requested = pyqtSignal()
    tts_prev_requested = pyqtSignal()
    tts_next_requested = pyqtSignal()
    tts_speed_change_requested = pyqtSignal(float)  # delta (+0.25 or -0.25)
    input_device_changed = pyqtSignal(object)
    output_device_changed = pyqtSignal(object)
    wake_word_toggled = pyqtSignal(bool)
    api_key_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._current_state = "idle"
        self._recording_active = False
        self._flash_on = False
        self._current_sentence = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # --- Audio settings ---
        self._audio_settings_toggle = QToolButton()
        self._audio_settings_toggle.setText("Audio Settings")
        self._audio_settings_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._audio_settings_toggle.setCheckable(True)
        self._audio_settings_toggle.setChecked(False)
        self._audio_settings_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._audio_settings_toggle.setStyleSheet(
            "QToolButton { color:#d4d4d4; background:#2d2d2d; border:1px solid #3c3c3c;"
            " padding:4px 8px; border-radius:3px; font-family:Consolas; font-size:11px; }"
            "QToolButton:hover { background:#3c3c3c; }"
        )
        self._audio_settings_toggle.clicked.connect(self._on_audio_settings_toggled)
        layout.addWidget(self._audio_settings_toggle)

        self._audio_settings_panel = QWidget()
        self._audio_settings_panel.hide()
        audio_layout = QGridLayout(self._audio_settings_panel)
        audio_layout.setContentsMargins(4, 0, 4, 4)
        audio_layout.setHorizontalSpacing(8)
        audio_layout.setVerticalSpacing(6)

        audio_layout.addWidget(QLabel("Input Device"), 0, 0)
        self._input_device_combo = QComboBox()
        self._input_device_combo.currentIndexChanged.connect(self._on_input_device_changed)
        audio_layout.addWidget(self._input_device_combo, 0, 1)

        audio_layout.addWidget(QLabel("Output Device"), 1, 0)
        self._output_device_combo = QComboBox()
        self._output_device_combo.currentIndexChanged.connect(self._on_output_device_changed)
        audio_layout.addWidget(self._output_device_combo, 1, 1)

        self._wake_word_check = QCheckBox("Wake Word")
        self._wake_word_check.toggled.connect(self.wake_word_toggled)
        audio_layout.addWidget(self._wake_word_check, 2, 0, 1, 2)
        layout.addWidget(self._audio_settings_panel)

        # --- LLM settings ---
        self._llm_settings_toggle = QToolButton()
        self._llm_settings_toggle.setText("LLM Settings")
        self._llm_settings_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._llm_settings_toggle.setCheckable(True)
        self._llm_settings_toggle.setChecked(False)
        self._llm_settings_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._llm_settings_toggle.setStyleSheet(
            "QToolButton { color:#d4d4d4; background:#2d2d2d; border:1px solid #3c3c3c;"
            " padding:4px 8px; border-radius:3px; font-family:Consolas; font-size:11px; }"
            "QToolButton:hover { background:#3c3c3c; }"
        )
        self._llm_settings_toggle.clicked.connect(self._on_llm_settings_toggled)
        layout.addWidget(self._llm_settings_toggle)

        self._llm_settings_panel = QWidget()
        self._llm_settings_panel.hide()
        llm_layout = QGridLayout(self._llm_settings_panel)
        llm_layout.setContentsMargins(4, 0, 4, 4)
        llm_layout.setHorizontalSpacing(8)
        llm_layout.setVerticalSpacing(6)

        llm_layout.addWidget(QLabel("API Key"), 0, 0)
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Enter Gemini API key...")
        self._api_key_input.setFont(QFont("Consolas", 10))
        self._api_key_input.setStyleSheet(
            "QLineEdit { background:#252526; color:#d4d4d4; border:1px solid #3c3c3c;"
            " padding:4px 8px; border-radius:3px; }"
        )
        llm_layout.addWidget(self._api_key_input, 0, 1)

        self._api_key_save_btn = QPushButton("Save")
        self._api_key_save_btn.setStyleSheet(
            "QPushButton { background:#0e639c; color:white; padding:4px 12px;"
            " border-radius:3px; border:none; }"
            "QPushButton:hover { background:#1177bb; }"
        )
        self._api_key_save_btn.clicked.connect(self._on_api_key_save)
        llm_layout.addWidget(self._api_key_save_btn, 0, 2)
        layout.addWidget(self._llm_settings_panel)

        # --- Status indicator ---
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._recording_dot = QLabel("●")
        self._recording_dot.setStyleSheet("color:#f14c4c; font-size:16px;")
        self._recording_dot.hide()
        self._recording_dot_effect = QGraphicsOpacityEffect(self._recording_dot)
        self._recording_dot.setGraphicsEffect(self._recording_dot_effect)
        self._dot_animation = QPropertyAnimation(self._recording_dot_effect, b"opacity", self)
        self._dot_animation.setDuration(700)
        self._dot_animation.setStartValue(0.35)
        self._dot_animation.setEndValue(1.0)
        self._dot_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._dot_animation.setLoopCount(-1)
        status_row.addWidget(self._recording_dot)

        self._status = QLabel("idle")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setFont(QFont("Consolas", 11))
        status_row.addWidget(self._status, stretch=1)
        layout.addLayout(status_row)

        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(500)
        self._flash_timer.timeout.connect(self._toggle_flash)

        # --- Response log ---
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 11))
        self._log.setStyleSheet(
            "QPlainTextEdit { background:#1e1e1e; color:#d4d4d4; border:none; }"
        )
        self._log.setPlaceholderText("AI responses will appear here...")
        layout.addWidget(self._log, stretch=1)

        # --- TTS sentence display ---
        self._tts_sentence = QLabel("")
        self._tts_sentence.setWordWrap(True)
        self._tts_sentence.setTextFormat(Qt.TextFormat.RichText)
        self._tts_sentence.setFont(QFont("Consolas", 10))
        self._tts_sentence.setStyleSheet(
            "color:#ce9178; background:#252526; padding:4px; border-radius:3px;"
        )
        layout.addWidget(self._tts_sentence)

        # --- TTS playback controls ---
        tts_row = QHBoxLayout()
        tts_row.setSpacing(4)

        btn_style = (
            "QPushButton { background:#333333; color:#d4d4d4; padding:4px 8px;"
            " border-radius:3px; border:1px solid #555555; font-weight:bold; }"
            "QPushButton:hover { background:#444444; }"
            "QPushButton:disabled { color:#666666; border-color:#444444; }"
        )

        self._prev_btn = QPushButton("◄")
        self._prev_btn.setStyleSheet(btn_style)
        self._prev_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self.tts_prev_requested)
        tts_row.addWidget(self._prev_btn)

        self._play_btn = QPushButton("▶")
        self._play_btn.setStyleSheet(btn_style)
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self.tts_play_requested)
        tts_row.addWidget(self._play_btn)

        self._stop_btn = QPushButton("■")
        self._stop_btn.setStyleSheet(btn_style)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.tts_stop_requested)
        tts_row.addWidget(self._stop_btn)

        self._next_btn = QPushButton("►")
        self._next_btn.setStyleSheet(btn_style)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self.tts_next_requested)
        tts_row.addWidget(self._next_btn)

        tts_row.addStretch()

        self._speed_down_btn = QPushButton("-")
        self._speed_down_btn.setFixedWidth(28)
        self._speed_down_btn.setStyleSheet(btn_style)
        self._speed_down_btn.clicked.connect(lambda: self.tts_speed_change_requested.emit(-0.25))
        tts_row.addWidget(self._speed_down_btn)

        self._speed_label = QLabel("1.0x")
        self._speed_label.setFont(QFont("Consolas", 10))
        self._speed_label.setStyleSheet("color:#d4d4d4; padding:0 4px;")
        tts_row.addWidget(self._speed_label)

        self._speed_up_btn = QPushButton("+")
        self._speed_up_btn.setFixedWidth(28)
        self._speed_up_btn.setStyleSheet(btn_style)
        self._speed_up_btn.clicked.connect(lambda: self.tts_speed_change_requested.emit(0.25))
        tts_row.addWidget(self._speed_up_btn)

        tts_row.addStretch()

        self._chunk_label = QLabel("")
        self._chunk_label.setFont(QFont("Consolas", 10))
        self._chunk_label.setStyleSheet("color:#608b4e;")
        tts_row.addWidget(self._chunk_label)

        layout.addLayout(tts_row)

        # --- Manual input ---
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a query (fallback for no mic)...")
        self._input.setFont(QFont("Consolas", 11))
        self._input.setStyleSheet(
            "QLineEdit { background:#252526; color:#d4d4d4; border:1px solid #3c3c3c;"
            " padding:4px 8px; border-radius:3px; }"
        )
        self._input.returnPressed.connect(self._on_submit)
        input_row.addWidget(self._input, stretch=1)

        send_btn = QPushButton("Send")
        send_btn.setStyleSheet(
            "QPushButton { background:#0e639c; color:white; padding:4px 12px;"
            " border-radius:3px; border:none; }"
            "QPushButton:hover { background:#1177bb; }"
        )
        send_btn.clicked.connect(self._on_submit)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)

        # --- Pause button ---
        self._pause_btn = QPushButton("Pause Listening")
        self._pause_btn.setCheckable(True)
        self._pause_btn.setStyleSheet(
            "QPushButton { background:#c24038; color:white; padding:6px 16px;"
            " font-weight:bold; border-radius:3px; border:none; }"
            "QPushButton:checked { background:#388c2c; }"
            "QPushButton:hover { opacity:0.9; }"
        )
        self._pause_btn.clicked.connect(self._on_pause_toggle)
        layout.addWidget(self._pause_btn)

    # ------------------------------------------------------------------
    # Public slots for coordinator signals
    # ------------------------------------------------------------------
    def set_state(self, state: str) -> None:
        """Update the status label.  state: idle | listening | processing | speaking."""
        self._current_state = state
        self._status.setText(state.capitalize())
        self._sync_recording_indicator()

    def set_recording_active(self, active: bool) -> None:
        """Start or stop the recording indicator independent of text state."""
        self._recording_active = active
        self._sync_recording_indicator()

    def append_response(self, text: str) -> None:
        """Append an LLM response to the log."""
        self._log.appendPlainText(f"\n{'─' * 40}\n{text}\n")

    def append_transcription(self, text: str) -> None:
        """Show what the user said."""
        self._log.appendPlainText(f"🎤 You: {text}")

    # ------------------------------------------------------------------
    # TTS control slots
    # ------------------------------------------------------------------
    def enable_tts_controls(self, enabled: bool) -> None:
        """Enable or disable the TTS navigation buttons."""
        self._prev_btn.setEnabled(enabled)
        self._play_btn.setEnabled(enabled)
        self._stop_btn.setEnabled(enabled)
        self._next_btn.setEnabled(enabled)

    def set_audio_devices(
        self,
        input_devices: list[dict],
        output_devices: list[dict],
        selected_input=None,
        selected_output=None,
    ) -> None:
        """Populate input/output device combos without emitting change signals."""
        self._populate_device_combo(self._input_device_combo, input_devices, selected_input)
        self._populate_device_combo(self._output_device_combo, output_devices, selected_output)

    def set_wake_word_enabled(self, enabled: bool) -> None:
        """Update the wake-word checkbox without emitting toggled signals."""
        blocked = self._wake_word_check.blockSignals(True)
        self._wake_word_check.setChecked(bool(enabled))
        self._wake_word_check.blockSignals(blocked)

    def set_api_key(self, key: str) -> None:
        """Populate the API key field without emitting changed signal."""
        self._api_key_input.setText(key)

    def update_chunk_info(self, index: int, total: int, sentence: str) -> None:
        """Update the chunk counter and sentence display."""
        self._current_sentence = sentence
        self._chunk_label.setText(f"{index + 1} / {total}")
        self.clear_word_highlight()

    def update_speed_display(self, speed: float) -> None:
        """Update the speed label."""
        self._speed_label.setText(f"{speed:.2g}x")

    def highlight_word(self, word_index: int, word_count: int) -> None:
        """Render the current TTS sentence with one word highlighted."""
        words = self._current_sentence.split()
        if not words or word_index < 0 or word_index >= len(words):
            self.clear_word_highlight()
            return
        if word_count != len(words):
            word_count = len(words)
        rendered = []
        for index, word in enumerate(words):
            escaped = html.escape(word)
            if index == word_index:
                rendered.append(
                    '<span style="background:#ce9178; color:#ffffff;">'
                    f"{escaped}</span>"
                )
            else:
                rendered.append(escaped)
        self._tts_sentence.setText(" ".join(rendered))

    def clear_word_highlight(self) -> None:
        """Restore the TTS sentence without any highlighted word."""
        self._tts_sentence.setText(html.escape(self._current_sentence))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _on_submit(self):
        text = self._input.text().strip()
        if text:
            self._input.clear()
            self.text_submitted.emit(text)

    def _on_pause_toggle(self):
        self._paused = self._pause_btn.isChecked()
        self._pause_btn.setText("Resume Listening" if self._paused else "Pause Listening")
        self.pause_toggled.emit(self._paused)

    def _on_audio_settings_toggled(self) -> None:
        expanded = self._audio_settings_toggle.isChecked()
        self._audio_settings_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._audio_settings_panel.setVisible(expanded)

    def _on_llm_settings_toggled(self) -> None:
        expanded = self._llm_settings_toggle.isChecked()
        self._llm_settings_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self._llm_settings_panel.setVisible(expanded)

    def _on_api_key_save(self) -> None:
        key = self._api_key_input.text().strip()
        if key:
            self.api_key_changed.emit(key)

    def _on_input_device_changed(self) -> None:
        self.input_device_changed.emit(self._input_device_combo.currentData())

    def _on_output_device_changed(self) -> None:
        self.output_device_changed.emit(self._output_device_combo.currentData())

    def _populate_device_combo(self, combo: QComboBox, devices: list[dict], selected) -> None:
        blocked = combo.blockSignals(True)
        combo.clear()
        combo.addItem("System Default", None)
        for device in devices:
            combo.addItem(
                f"{device['name']} ({device['channels']} ch)",
                device["index"],
            )
        current_index = combo.findData(selected)
        combo.setCurrentIndex(current_index if current_index >= 0 else 0)
        combo.blockSignals(blocked)

    def _toggle_flash(self) -> None:
        self._flash_on = not self._flash_on
        self._update_status_style()

    def _sync_recording_indicator(self) -> None:
        should_flash = self._recording_active and self._current_state == "listening"
        if should_flash:
            if not self._flash_timer.isActive():
                self._flash_on = True
                self._flash_timer.start()
            self._recording_dot.show()
            if self._dot_animation.state() != QPropertyAnimation.State.Running:
                self._dot_animation.start()
        else:
            self._flash_timer.stop()
            self._flash_on = False
            self._recording_dot.hide()
            self._dot_animation.stop()
            self._recording_dot_effect.setOpacity(1.0)
        self._update_status_style()

    def _update_status_style(self) -> None:
        colors = {
            "idle": "#608b4e",
            "listening": "#4ec9b0",
            "loading": "#569cd6",
            "processing": "#dcdcaa",
            "speaking": "#ce9178",
        }
        background = "#252526"
        border = "transparent"
        if self._recording_active and self._current_state == "listening" and self._flash_on:
            background = "#0f3e40"
            border = "#4ec9b0"
        self._status.setStyleSheet(
            f"background:{background}; color:{colors.get(self._current_state, '#d4d4d4')};"
            f" padding:6px; border-radius:4px; border:1px solid {border};"
        )
