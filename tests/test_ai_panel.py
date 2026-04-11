"""Tests for ui/ai_panel.py — AiPanel widget."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtTest import QSignalSpy

from ui.ai_panel import AiPanel


@pytest.mark.ui
class TestAiPanel:
    """Verify AiPanel state display and signal wiring."""

    def test_initial_state_label(self, qapp):
        panel = AiPanel()
        assert panel._status.text() == "idle"

    def test_set_state_updates_label(self, qapp):
        panel = AiPanel()
        panel.set_state("listening")
        assert panel._status.text() == "Listening"

    def test_set_state_processing(self, qapp):
        panel = AiPanel()
        panel.set_state("processing")
        assert panel._status.text() == "Processing"

    def test_set_state_speaking(self, qapp):
        panel = AiPanel()
        panel.set_state("speaking")
        assert panel._status.text() == "Speaking"

    def test_set_state_loading(self, qapp):
        panel = AiPanel()
        panel.set_state("loading")
        assert panel._status.text() == "Loading"

    def test_append_response(self, qapp):
        panel = AiPanel()
        panel.append_response("Hello from LLM")
        log_text = panel._log.toPlainText()
        assert "Hello from LLM" in log_text

    def test_append_transcription(self, qapp):
        panel = AiPanel()
        panel.append_transcription("fix the bug")
        log_text = panel._log.toPlainText()
        assert "fix the bug" in log_text

    def test_text_submitted_signal(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.text_submitted)

        panel._input.setText("test query")
        panel._on_submit()

        assert len(spy) == 1
        assert spy[0][0] == "test query"

    def test_submit_clears_input(self, qapp):
        panel = AiPanel()
        panel._input.setText("test query")
        panel._on_submit()
        assert panel._input.text() == ""

    def test_empty_submit_does_not_emit(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.text_submitted)

        panel._input.setText("")
        panel._on_submit()

        assert len(spy) == 0

    def test_pause_toggle(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.pause_toggled)

        panel._pause_btn.setChecked(True)
        panel._on_pause_toggle()

        assert len(spy) == 1
        assert spy[0][0] is True
        assert panel._pause_btn.text() == "Resume Listening"

    def test_resume_toggle(self, qapp):
        panel = AiPanel()

        # Pause first.
        panel._pause_btn.setChecked(True)
        panel._on_pause_toggle()

        # Then resume.
        panel._pause_btn.setChecked(False)
        panel._on_pause_toggle()

        assert panel._pause_btn.text() == "Pause Listening"


# =====================================================================
# TTS Playback Controls (Phase 4)
# =====================================================================

@pytest.mark.ui
class TestTtsControls:
    """Verify TTS navigation and playback controls in AiPanel."""

    def test_tts_controls_exist(self, qapp):
        panel = AiPanel()
        assert hasattr(panel, "_prev_btn")
        assert hasattr(panel, "_play_btn")
        assert hasattr(panel, "_stop_btn")
        assert hasattr(panel, "_next_btn")
        assert hasattr(panel, "_speed_label")
        assert hasattr(panel, "_chunk_label")

    def test_tts_controls_initially_disabled(self, qapp):
        panel = AiPanel()
        assert not panel._prev_btn.isEnabled()
        assert not panel._play_btn.isEnabled()
        assert not panel._stop_btn.isEnabled()
        assert not panel._next_btn.isEnabled()

    def test_enable_tts_controls(self, qapp):
        panel = AiPanel()
        panel.enable_tts_controls(True)
        assert panel._play_btn.isEnabled()
        assert panel._prev_btn.isEnabled()
        assert panel._next_btn.isEnabled()

    def test_disable_tts_controls(self, qapp):
        panel = AiPanel()
        panel.enable_tts_controls(True)
        panel.enable_tts_controls(False)
        assert not panel._play_btn.isEnabled()
        assert not panel._prev_btn.isEnabled()
        assert not panel._next_btn.isEnabled()

    def test_update_chunk_label(self, qapp):
        panel = AiPanel()
        panel.update_chunk_info(2, 5, "Hello world.")
        assert "3 / 5" in panel._chunk_label.text()

    def test_update_chunk_label_shows_sentence(self, qapp):
        panel = AiPanel()
        panel.update_chunk_info(0, 3, "Test sentence.")
        assert "Test sentence." in panel._tts_sentence.text()

    def test_update_speed_label(self, qapp):
        panel = AiPanel()
        panel.update_speed_display(1.5)
        assert "1.5" in panel._speed_label.text()

    def test_play_requested_signal(self, qapp):
        panel = AiPanel()
        panel.enable_tts_controls(True)
        spy = QSignalSpy(panel.tts_play_requested)
        panel._play_btn.click()
        assert len(spy) == 1

    def test_stop_requested_signal(self, qapp):
        panel = AiPanel()
        panel.enable_tts_controls(True)
        panel._stop_btn.setEnabled(True)
        spy = QSignalSpy(panel.tts_stop_requested)
        panel._stop_btn.click()
        assert len(spy) == 1

    def test_prev_requested_signal(self, qapp):
        panel = AiPanel()
        panel.enable_tts_controls(True)
        spy = QSignalSpy(panel.tts_prev_requested)
        panel._prev_btn.click()
        assert len(spy) == 1

    def test_next_requested_signal(self, qapp):
        panel = AiPanel()
        panel.enable_tts_controls(True)
        spy = QSignalSpy(panel.tts_next_requested)
        panel._next_btn.click()
        assert len(spy) == 1

    def test_speed_up_signal(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.tts_speed_change_requested)
        panel._speed_up_btn.click()
        assert len(spy) == 1
        assert spy[0][0] > 0  # positive delta = speed up

    def test_speed_down_signal(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.tts_speed_change_requested)
        panel._speed_down_btn.click()
        assert len(spy) == 1
        assert spy[0][0] < 0  # negative delta = slow down


@pytest.mark.ui
class TestAudioSettingsControls:
    def test_audio_settings_toggle_shows_text(self, qapp):
        panel = AiPanel()
        style = panel._audio_settings_toggle.toolButtonStyle()
        assert style == Qt.ToolButtonStyle.ToolButtonTextBesideIcon

    def test_audio_settings_widgets_exist(self, qapp):
        panel = AiPanel()
        assert hasattr(panel, "_input_device_combo")
        assert hasattr(panel, "_output_device_combo")
        assert hasattr(panel, "_wake_word_check")

    def test_set_audio_devices_populates_combos(self, qapp):
        panel = AiPanel()
        panel.set_audio_devices(
            [{"index": 1, "name": "Mic", "channels": 2}],
            [{"index": 2, "name": "Speaker", "channels": 2}],
            selected_input=1,
            selected_output=2,
        )

        assert panel._input_device_combo.count() == 2
        assert panel._output_device_combo.count() == 2
        assert panel._input_device_combo.currentData() == 1
        assert panel._output_device_combo.currentData() == 2

    def test_input_device_changed_signal(self, qapp):
        panel = AiPanel()
        panel.set_audio_devices(
            [{"index": 3, "name": "Mic", "channels": 1}],
            [],
            selected_input=None,
            selected_output=None,
        )
        spy = QSignalSpy(panel.input_device_changed)

        panel._input_device_combo.setCurrentIndex(1)

        assert len(spy) == 1
        assert spy[0][0] == 3

    def test_output_device_changed_signal(self, qapp):
        panel = AiPanel()
        panel.set_audio_devices(
            [],
            [{"index": 4, "name": "Speaker", "channels": 2}],
            selected_input=None,
            selected_output=None,
        )
        spy = QSignalSpy(panel.output_device_changed)

        panel._output_device_combo.setCurrentIndex(1)

        assert len(spy) == 1
        assert spy[0][0] == 4

    def test_wake_word_toggled_signal(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.wake_word_toggled)

        panel._wake_word_check.setChecked(True)

        assert len(spy) == 1
        assert spy[0][0] is True


@pytest.mark.ui
class TestRecordingIndicator:
    def test_recording_active_starts_flash_when_listening(self, qapp):
        panel = AiPanel()
        panel.set_state("listening")

        panel.set_recording_active(True)

        assert panel._flash_timer.isActive()
        assert not panel._recording_dot.isHidden()

    def test_recording_active_stops_flash_when_state_changes(self, qapp):
        panel = AiPanel()
        panel.set_state("listening")
        panel.set_recording_active(True)

        panel.set_state("processing")

        assert not panel._flash_timer.isActive()

    def test_recording_inactive_hides_indicator(self, qapp):
        panel = AiPanel()
        panel.set_state("listening")
        panel.set_recording_active(True)

        panel.set_recording_active(False)

        assert not panel._flash_timer.isActive()
        assert panel._recording_dot.isHidden()


@pytest.mark.ui
class TestTtsWordHighlight:
    def test_highlight_word_renders_html(self, qapp):
        panel = AiPanel()
        panel.update_chunk_info(0, 3, "hello brave world")

        panel.highlight_word(1, 3)

        assert "background:#ce9178" in panel._tts_sentence.text()
        assert "brave" in panel._tts_sentence.text()

    def test_clear_word_highlight_restores_plain_sentence(self, qapp):
        panel = AiPanel()
        panel.update_chunk_info(0, 2, "hello world")
        panel.highlight_word(0, 2)

        panel.clear_word_highlight()

        assert "span style" not in panel._tts_sentence.text()
        assert "hello world" in panel._tts_sentence.text()


@pytest.mark.ui
class TestLlmSettingsControls:
    """Verify LLM Settings section in AiPanel."""

    def test_llm_settings_widgets_exist(self, qapp):
        panel = AiPanel()
        assert hasattr(panel, "_llm_settings_toggle")
        assert hasattr(panel, "_api_key_input")
        assert hasattr(panel, "_api_key_save_btn")

    def test_api_key_input_is_password_mode(self, qapp):
        panel = AiPanel()
        assert panel._api_key_input.echoMode() == QLineEdit.EchoMode.Password

    def test_api_key_changed_signal_on_save(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.api_key_changed)

        panel._api_key_input.setText("my-api-key")
        panel._on_api_key_save()

        assert len(spy) == 1
        assert spy[0][0] == "my-api-key"

    def test_api_key_save_ignores_empty(self, qapp):
        panel = AiPanel()
        spy = QSignalSpy(panel.api_key_changed)

        panel._api_key_input.setText("")
        panel._on_api_key_save()

        assert len(spy) == 0

    def test_set_api_key_populates_field(self, qapp):
        panel = AiPanel()
        panel.set_api_key("pre-loaded-key")
        assert panel._api_key_input.text() == "pre-loaded-key"

    def test_llm_settings_panel_initially_hidden(self, qapp):
        panel = AiPanel()
        assert panel._llm_settings_panel.isHidden()

    def test_llm_settings_toggle_shows_panel(self, qapp):
        panel = AiPanel()
        panel._llm_settings_toggle.setChecked(True)
        panel._on_llm_settings_toggled()
        assert not panel._llm_settings_panel.isHidden()
