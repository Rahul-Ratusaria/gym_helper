"""Native desktop workout studio with background camera inference."""
from datetime import datetime
import html
import json
import os
from math import ceil
from pathlib import Path
import time

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from camera import CameraWorker
from coaching import Coach, Observation
from demo import demo_pose
from storage import History
from tracker import EXERCISES
from widgets import AngleChart, Metric, RepRing, STYLE, VideoCanvas, label
from workout import Workout

ROOT = Path(__file__).resolve().parent


def button(text, callback, primary=False):
    item = QPushButton(text)
    if primary:
        item.setObjectName("primary")
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.clicked.connect(callback)
    return item


def card():
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 16, 18, 16)
    box.setSpacing(12)
    return frame, box


def wrapped(text, role="muted"):
    item = label(text, role)
    item.setWordWrap(True)
    return item


def spin(low, high, value, suffix=""):
    item = QSpinBox()
    item.setRange(low, high)
    item.setValue(value)
    item.setSuffix(suffix)
    return item


class GymWindow(QMainWindow):
    def __init__(self, data_dir=None, exercise="curl", camera=0, side="auto"):
        super().__init__()
        # Offscreen rendering on Windows may not enumerate system fonts.
        if not QFontDatabase.families():
            font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            for filename in ("segoeui.ttf", "seguisb.ttf", "segoeuib.ttf"):
                if (font_dir / filename).is_file():
                    QFontDatabase.addApplicationFont(str(font_dir / filename))
        self.setWindowTitle("Gym Helper — Movement Studio")
        self.resize(1440, 960)
        self.setMinimumSize(1140, 760)
        self.setStyleSheet(STYLE)
        self.data_dir = Path(data_dir) if data_dir else ROOT / "data"
        self.history = History(self.data_dir / "workouts.sqlite3")
        self.settings = QSettings(str(self.data_dir / "preferences.ini"), QSettings.Format.IniFormat)
        self.worker = None
        self.workout = None
        self.coach = Coach(exercise, side)
        self.observation = Observation()
        self.pending = self.closing = self.saved = False
        self.video_path = ""
        self.source_kind = "Webcam"
        self.started = ""
        self.last_voice = 0
        self.voice = None
        self.demo_time = 0
        self.last_ui_tick = time.monotonic()
        self.last_packet = 0
        self._build(exercise, camera, side)
        self._restore()
        self._exercise_changed()
        self._refresh_history()
        self._shortcuts()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)
        self.statusBar().showMessage("Ready · Camera opens only when you start a session.")

    def _build(self, exercise, camera, side):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(198)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(20, 28, 20, 22)
        nav.setSpacing(12)
        logo_row = QHBoxLayout()
        logo = label("g.", "logo")
        logo.setFixedSize(43, 43)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_row.addWidget(logo)
        logo_row.addWidget(label("gym\nhelper", "brand"))
        nav.addLayout(logo_row)
        nav.addSpacing(36)
        nav.addWidget(label("YOUR WORKSPACE", "eyebrow"))
        self.nav_buttons = []
        for i, title in enumerate(("01   Train", "02   Activity", "03   Exercise guide")):
            item = button(title, lambda checked=False, index=i: self._page(index))
            item.setObjectName("nav")
            item.setCheckable(True)
            self.nav_buttons.append(item)
            nav.addWidget(item)
        self.nav_buttons[0].setChecked(True)
        nav.addStretch()
        nav.addWidget(wrapped("BUILT FOR\nBETTER MOVEMENT", "eyebrow"))
        nav.addWidget(wrapped("Small steps.\nStronger every session.", "small"))
        nav.addSpacing(16)
        nav.addWidget(label("●  On-device processing", "small"))
        nav.addWidget(label("MOVEMENT STUDIO  /  1.0", "eyebrow"))
        shell.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(28, 24, 28, 18)
        main.setSpacing(18)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(5)
        title_box.addWidget(label("MOVE WITH INTENTION", "eyebrow"))
        self.page_title = label("Let's get stronger.", "pageTitle")
        title_box.addWidget(self.page_title)
        heading.addLayout(title_box)
        heading.addStretch()
        self.demo_button = button("Explore demo", self.start_demo)
        self.demo_button.setObjectName("quiet")
        heading.addWidget(self.demo_button)
        heading.addSpacing(12)
        heading.addWidget(label("LOCAL PROCESSING", "badge"))
        main.addLayout(heading)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._training_page(exercise, camera, side))
        self.pages.addWidget(self._history_page())
        self.pages.addWidget(self._guide_page())
        main.addWidget(self.pages, 1)
        shell.addLayout(main, 1)

    def _training_page(self, exercise, camera, side):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        left_panel = QWidget()
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 2, 0)
        left.setSpacing(14)
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.total_metric = Metric("Session reps", "00", "Every complete movement", True)
        self.time_metric = Metric("Active time", "00:00", "Excludes pauses & rests")
        self.set_metric = Metric("Current set", "1 / 3", "12 reps per set")
        for item in (self.total_metric, self.time_metric, self.set_metric):
            metrics.addWidget(item, 1)
        left.addLayout(metrics)
        video_top = QHBoxLayout()
        self.exercise_title = label("Bicep curl", "sectionTitle")
        video_top.addWidget(self.exercise_title)
        video_top.addStretch()
        self.tracking_label = label("●  Waiting for session", "small")
        video_top.addWidget(self.tracking_label)
        left.addLayout(video_top)
        self.canvas = VideoCanvas()
        left.addWidget(self.canvas, 1)
        controls = QHBoxLayout()
        self.start_button = button("Start session  →", self.start_session, True)
        self.pause_button = button("Pause", self.toggle_pause)
        self.end_button = button("Finish && save", self.finish_session)
        self.skip_button = button("Skip rest", self.skip_rest)
        self.pause_button.setEnabled(False)
        self.end_button.setEnabled(False)
        self.skip_button.setVisible(False)
        for widget, stretch in ((self.start_button, 2), (self.pause_button, 1), (self.end_button, 1), (self.skip_button, 0)):
            controls.addWidget(widget, stretch)
        left.addLayout(controls)
        self.coach_card = QFrame()
        self.coach_card.setObjectName("coach")
        feedback = QVBoxLayout(self.coach_card)
        feedback.setContentsMargins(17, 14, 17, 14)
        feedback.setSpacing(6)
        feedback.addWidget(label("LIVE COACH  /  CAMERA ESTIMATES", "eyebrow"))
        self.cue_title = wrapped("A little setup goes a long way.", "coachTitle")
        self.cue_detail = wrapped("Choose your exercise, position your camera, then start.")
        feedback.addWidget(self.cue_title)
        feedback.addWidget(self.cue_detail)
        left.addWidget(self.coach_card)
        chart_card, chart_box = card()
        chart_head = QHBoxLayout()
        chart_head.addWidget(label("Movement trace", "sectionTitle"))
        chart_head.addStretch()
        self.angle_label = label("—°", "summary")
        chart_head.addWidget(self.angle_label)
        chart_box.addLayout(chart_head)
        self.chart = AngleChart()
        chart_box.addWidget(self.chart)
        self.chart_note = label("Joint angle · dashed lines mark counting endpoints", "small")
        chart_box.addWidget(self.chart_note)
        left.addWidget(chart_card)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setWidget(left_panel)
        layout.addWidget(left_scroll, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(296)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        panel = QWidget()
        right = QVBoxLayout(panel)
        right.setContentsMargins(0, 0, 3, 0)
        right.setSpacing(14)
        progress_card, progress = card()
        top = QHBoxLayout()
        top.addWidget(label("YOUR SET", "eyebrow"))
        top.addStretch()
        self.phase_label = label("READY", "small")
        top.addWidget(self.phase_label)
        progress.addLayout(top)
        self.ring = RepRing()
        progress.addWidget(self.ring)
        self.range_bar = QProgressBar()
        self.range_bar.setRange(0, 100)
        self.range_bar.setTextVisible(False)
        progress.addWidget(self.range_bar)
        self.range_label = label("Movement depth  ·  —", "small")
        progress.addWidget(self.range_label)
        right.addWidget(progress_card)
        self.setup_card, setup = card()
        setup.addWidget(label("Make it your session", "sectionTitle"))
        setup.addWidget(label("Exercise", "small"))
        self.exercise_combo = QComboBox()
        for key, profile in EXERCISES.items():
            self.exercise_combo.addItem(profile.title, key)
        self.exercise_combo.setCurrentIndex(list(EXERCISES).index(exercise))
        self.exercise_combo.currentIndexChanged.connect(self._exercise_changed)
        setup.addWidget(self.exercise_combo)
        self.position_hint = wrapped("")
        setup.addWidget(self.position_hint)
        grid = QGridLayout()
        grid.setSpacing(9)
        self.sets_spin = spin(1, 10, 3)
        self.reps_spin = spin(1, 100, 12)
        self.rest_spin = spin(0, 300, 45, " s")
        self.side_combo = QComboBox()
        self.side_combo.addItems(["Auto · per set", "Left", "Right"])
        self.side_combo.setCurrentIndex({"auto": 0, "left": 1, "right": 2}[side])
        fields = (("Sets", self.sets_spin, "Reps / set", self.reps_spin), ("Rest", self.rest_spin, "Tracked side", self.side_combo))
        for row, (name_a, control_a, name_b, control_b) in enumerate(fields):
            grid.addWidget(label(name_a, "small"), row * 2, 0)
            grid.addWidget(label(name_b, "small"), row * 2, 1)
            grid.addWidget(control_a, row * 2 + 1, 0)
            grid.addWidget(control_b, row * 2 + 1, 1)
        setup.addLayout(grid)
        self.reps_spin.valueChanged.connect(self._goals_changed)
        self.sets_spin.valueChanged.connect(self._goals_changed)
        setup.addWidget(label("Input source", "small"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["Webcam", "Video file", "Interactive demo"])
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        setup.addWidget(self.source_combo)
        self.camera_spin = spin(0, 9, camera)
        self.camera_spin.setPrefix("Camera  ")
        setup.addWidget(self.camera_spin)
        self.file_button = button("Choose video…", self.choose_video)
        self.file_button.setVisible(False)
        setup.addWidget(self.file_button)
        self.file_label = wrapped("No video selected", "small")
        self.file_label.setVisible(False)
        setup.addWidget(self.file_label)
        self.mirror_check = QCheckBox("Mirror preview")
        self.mirror_check.setChecked(True)
        self.mirror_check.setToolTip("Preview only. Left and right refer to your body.")
        self.mirror_check.toggled.connect(self._display_options)
        self.skeleton_check = QCheckBox("Show pose overlay")
        self.skeleton_check.setChecked(True)
        self.skeleton_check.toggled.connect(self._display_options)
        self.voice_check = QCheckBox("Speak rep and rest cues")
        self.voice_check.toggled.connect(self._voice_changed)
        for control in (self.mirror_check, self.skeleton_check, self.voice_check):
            setup.addWidget(control)
        self.tune_button = button("Adjust counting endpoints", self._toggle_tuning)
        self.tune_button.setObjectName("quiet")
        setup.addWidget(self.tune_button)
        self.tuning = QWidget()
        tuning = QVBoxLayout(self.tuning)
        tuning.setContentsMargins(0, 0, 0, 0)
        tuning.addWidget(wrapped("Angle thresholds are heuristics. Adjust to your range and camera setup.", "small"))
        endpoints = QHBoxLayout()
        self.low_spin = spin(20, 140, 55, "°")
        self.high_spin = spin(80, 180, 155, "°")
        endpoints.addWidget(self.low_spin)
        endpoints.addWidget(self.high_spin)
        self.low_spin.setToolTip("Bent endpoint")
        self.high_spin.setToolTip("Extended endpoint")
        tuning.addLayout(endpoints)
        tuning.addWidget(button("Restore exercise defaults", self._reset_thresholds))
        self.tuning.setVisible(False)
        setup.addWidget(self.tuning)
        right.addWidget(self.setup_card)
        right.addWidget(wrapped("Form cues are single-camera estimates. Reps do not certify correct technique.", "small"))
        right.addStretch()
        scroll.setWidget(panel)
        layout.addWidget(scroll)
        return page

    def _history_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(wrapped("Your real sessions, saved on this computer. Demo sessions stay out of your activity."))
        head.addStretch()
        self.export_button = button("Export CSV  ↗", self.export_history)
        head.addWidget(self.export_button)
        box.addLayout(head)
        metrics = QHBoxLayout()
        self.history_count = Metric("Sessions", "0", "Webcam + video sessions")
        self.history_reps = Metric("Total reps", "0", "Across all saved sessions", True)
        self.history_minutes = Metric("Active minutes", "0", "Time spent in active sets")
        for item in (self.history_count, self.history_reps, self.history_minutes):
            metrics.addWidget(item)
        box.addLayout(metrics)
        self.history_empty = wrapped("A fresh start. Finish your first camera or video session to see it here.", "summary")
        box.addWidget(self.history_empty)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Date & time", "Exercise", "Source", "Reps", "Full sets", "Active time"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._history_detail)
        box.addWidget(self.table, 1)
        self.history_detail = QTextBrowser()
        self.history_detail.setMaximumHeight(210)
        self.history_detail.setHtml("<p style='color:#929b99'>Select a session to inspect per-rep timing and workout settings.</p>")
        box.addWidget(self.history_detail)
        return page

    def _guide_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(wrapped("Five movements. A clear setup. Start with a range you can control."))
        self.guide_select = QComboBox()
        for key, profile in EXERCISES.items():
            self.guide_select.addItem(profile.title, key)
        self.guide_select.currentIndexChanged.connect(self._guide_changed)
        box.addWidget(self.guide_select)
        self.guide_text = QTextBrowser()
        box.addWidget(self.guide_text, 1)
        box.addWidget(button("Train this exercise  →", self._train_selected, True), alignment=Qt.AlignmentFlag.AlignLeft)
        self._guide_changed()
        return page

    def _page(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav_buttons):
            nav.setChecked(i == index)
        self.page_title.setText(("Let's get stronger.", "Your work adds up.", "Move with confidence.")[index])
        if index == 1:
            self._refresh_history()

    def _guide_changed(self):
        profile = EXERCISES[self.guide_select.currentData()]
        steps = "".join(f"<li style='margin-bottom:18px'>{html.escape(step)}</li>" for step in profile.steps)
        self.guide_text.setHtml(f"""<h4 style='color:#b6f36b'>{profile.group.upper()}</h4>
            <h1>{profile.title}</h1><p style='font-size:16px;color:#b9c8b1'>{profile.setup}</p>
            <hr><h2>The movement</h2><ol style='font-size:16px'>{steps}</ol>
            <h2>How counting works</h2><p>Begin at the extended endpoint ({profile.high}°), reach the bent endpoint
            ({profile.low}°), then return to extension. Hold each endpoint briefly. Only your selected side is measured.</p>
            <h2>Give the camera a clear view</h2><p>Use good lighting, a stable camera and a side view. Keep one person in frame.
            Auto side selection locks onto the more visible side for each set. To change sides mid-set, finish the session first.</p>
            <h2>Understand the feedback</h2><p>Landmark confidence describes visibility, not exercise quality. Form cues use simple
            angle rules and can be affected by perspective. A counted rep indicates the angle endpoints were reached;
            it does not verify the full movement. Adjust endpoints before starting if needed.</p>
            <p style='color:#b6f36b'>Space: pause/resume · Escape: finish · Ctrl+1/2/3: navigate.</p>""")

    def _train_selected(self):
        if not self._busy():
            self.exercise_combo.setCurrentIndex(self.guide_select.currentIndex())
        self._page(0)

    def _exercise_changed(self, *_):
        if not hasattr(self, "chart"):
            return
        profile = EXERCISES[self.exercise_combo.currentData()]
        self.exercise_title.setText(profile.title)
        self.position_hint.setText(profile.setup)
        self._reset_thresholds()
        self.chart.clear()

    def _reset_thresholds(self):
        if hasattr(self, "low_spin"):
            profile = EXERCISES[self.exercise_combo.currentData()]
            self.low_spin.setValue(int(profile.low))
            self.high_spin.setValue(int(profile.high))
            self.chart.low, self.chart.high = profile.low, profile.high
            self.chart.update()

    def _toggle_tuning(self):
        self.tuning.setVisible(not self.tuning.isVisible())

    def _goals_changed(self):
        if not self._busy():
            self.ring.set_values(0, self.reps_spin.value())
            self.set_metric.value.setText(f"1 / {self.sets_spin.value()}")
            self.set_metric.subtitle.setText(f"{self.reps_spin.value()} reps per set")

    def _source_changed(self, index):
        self.camera_spin.setVisible(index == 0)
        self.file_button.setVisible(index == 1)
        self.file_label.setVisible(index == 1)

    def _display_options(self):
        self.canvas.mirror = self.mirror_check.isChecked()
        self.canvas.skeleton = self.skeleton_check.isChecked()
        self.canvas.update()

    def choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a workout video", "", "Video files (*.mp4 *.avi *.mov *.mkv *.webm);;All files (*)")
        if path:
            self.video_path = path
            self.file_label.setText(Path(path).name)
            self.file_label.setToolTip(path)

    def _voice_changed(self, enabled):
        if not enabled:
            if self.voice:
                self.voice.stop()
            return
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self.voice = self.voice or QTextToSpeech(self)
            if self.voice.state() == QTextToSpeech.State.Error:
                raise RuntimeError("No system speech voice is available.")
            self.voice.setRate(0.05)
        except Exception as exc:
            self.voice_check.setChecked(False)
            self.statusBar().showMessage(f"Voice unavailable: {exc}", 10000)

    def _say(self, text):
        if self.voice and self.voice_check.isChecked():
            self.voice.stop()
            self.voice.say(text)

    def _busy(self):
        return self.pending or (self.workout is not None and self.workout.state not in ("idle", "complete"))

    def _lock_setup(self, locked):
        for item in (self.exercise_combo, self.sets_spin, self.reps_spin, self.rest_spin,
                     self.side_combo, self.source_combo, self.camera_spin, self.file_button,
                     self.tune_button, self.low_spin, self.high_spin):
            item.setEnabled(not locked)
        self.start_button.setEnabled(not locked)
        self.demo_button.setEnabled(not locked)
        self.pause_button.setEnabled(locked and not self.pending)
        self.end_button.setEnabled(locked)

    def start_demo(self):
        if self._busy() or self.worker is not None:
            self._page(0)
            return
        self.source_combo.setCurrentIndex(2)
        self._page(0)
        self.start_session()

    def start_session(self):
        if self._busy() or self.worker is not None:
            return
        self.source_kind = self.source_combo.currentText()
        if self.source_kind == "Video file" and not self.video_path:
            self.choose_video()
            if not self.video_path:
                return
        try:
            self.coach = Coach(self.exercise_combo.currentData(), ("auto", "left", "right")[self.side_combo.currentIndex()], self.low_spin.value(), self.high_spin.value())
        except ValueError as exc:
            QMessageBox.information(self, "Adjust counting endpoints", str(exc))
            return
        self.workout = Workout(self.reps_spin.value(), self.sets_spin.value(), self.rest_spin.value())
        self.session_settings = {"target": self.workout.target, "sets": self.workout.sets, "rest_seconds": self.workout.rest_seconds,
                                 "side": self.coach.requested_side, "bent_endpoint": self.low_spin.value(), "extended_endpoint": self.high_spin.value()}
        self.started = datetime.now().astimezone().isoformat(timespec="seconds")
        self.saved = False
        self.demo_time = 0
        self.end_button.setText("Finish && save")
        self.observation = Observation()
        self._show_observation()
        self.chart.clear()
        self.chart.low, self.chart.high = self.low_spin.value(), self.high_spin.value()
        self.canvas.set_frame(None, [])
        self.canvas.center_title = "Getting your session ready…"
        self.canvas.center_detail = "Starting the pose engine. This can take a few seconds."
        self.canvas.is_demo = self.source_kind == "Interactive demo"
        self.chart_note.setText("SIMULATED movement · demonstration only" if self.canvas.is_demo else "Joint angle · dashed lines mark counting endpoints")
        self.pending = True
        self._lock_setup(True)
        self.cue_title.setText("Preparing your session")
        self.cue_detail.setText("Keep your working joints in frame.")
        self.canvas.banner = "SIMULATION · NOT CAMERA DATA" if self.canvas.is_demo else "INITIALIZING POSE ENGINE"
        if self.canvas.is_demo:
            self._source_ready()
        else:
            source = self.video_path if self.source_kind == "Video file" else self.camera_spin.value()
            self.worker = CameraWorker(source, ROOT / "models/pose_landmarker_lite.task", self)
            self.worker.pause_video(True)
            self.worker.ready.connect(self._source_ready)
            self.worker.problem.connect(self._source_error)
            self.worker.ended.connect(self._video_ended)
            self.worker.finished.connect(self._worker_finished)
            self.worker.start()
        self.last_packet = time.monotonic()
        self._update_metrics(time.monotonic())

    def _source_ready(self):
        if not self.pending or self.closing:
            return
        self.pending = False
        self.workout.start(time.monotonic())
        self.pause_button.setEnabled(True)
        self.canvas.banner = "SIMULATION · NOT CAMERA DATA" if self.canvas.is_demo else self.source_kind.upper() + " · LIVE POSE"
        self.cue_title.setText("Find your starting position")
        self.cue_detail.setText(EXERCISES[self.coach.key].setup)
        self.statusBar().showMessage("Demo · synthetic landmarks · activity will not be saved." if self.canvas.is_demo else "Session running · frames are processed locally and are not saved.")

    def _tick(self):
        now = time.monotonic()
        dt, self.last_ui_tick = min(.15, now - self.last_ui_tick), now
        if self.pending or not self.workout or self.workout.state == "complete":
            return
        transition = self.workout.tick(now)
        if transition == "new_set":
            self.coach.new_set()
            self.observation = Observation()
            self.chart.clear()
            self._say(f"Set {self.workout.set_number}. Let's go.")
        elif transition == "begin":
            self._say("Let's begin.")
        if self.worker:
            self.worker.pause_video(self.workout.state != "active")
            packet = self.worker.take()
            if packet:
                rgb, landmarks, media_time, fps = packet
                self.last_packet = now
                height, width, _ = rgb.shape
                self.canvas.set_frame(rgb, landmarks)
                self._analyze(landmarks, width, height, media_time, now)
                self.tracking_label.setText(f"●  {fps:.0f} inference fps  ·  {self.observation.side}")
            elif self.workout.state == "active" and now - self.last_packet > 1:
                self.coach.interrupt()
                self.observation = Observation(cue="Waiting for camera frames", detail="Check the camera connection or finish and restart the source.")
                self.canvas.points = []
                self._show_observation()
        elif self.canvas.is_demo:
            if self.workout.state == "active":
                self.demo_time += dt
            landmarks = demo_pose(self.coach.key, self.demo_time, "right" if self.coach.requested_side == "right" else "left")
            self.canvas.set_frame(None, landmarks)
            self._analyze(landmarks, 1280, 720, now, now)
            self.tracking_label.setText("●  Synthetic landmarks  ·  demo")
        self._update_metrics(now)

    def _analyze(self, landmarks, width, height, media_time, wall_time):
        if self.workout.state != "active":
            return
        self.observation = self.coach.process(landmarks, width, height, media_time)
        obs = self.observation
        self.chart.add(wall_time, obs.angle)
        if obs.counted:
            self.workout.record_rep(wall_time, obs.angle, obs.duration, obs.side)
            self._say(str(self.workout.current_reps))
            if self.workout.state == "rest":
                self.coach.interrupt()
                self._say(f"Set complete. Rest for {self.workout.rest_seconds} seconds.")
            elif self.workout.state == "complete":
                self.finish_session()
        elif obs.warning and wall_time - self.last_voice > 10:
            self._say(obs.cue)
            self.last_voice = wall_time
        if self.workout.state != "complete":
            self._show_observation()

    def _show_observation(self):
        obs = self.observation
        self.cue_title.setText(obs.cue)
        self.cue_detail.setText(obs.detail)
        if self.coach_card.property("warning") != obs.warning:
            self.coach_card.setProperty("warning", obs.warning)
            self.coach_card.style().unpolish(self.coach_card)
            self.coach_card.style().polish(self.coach_card)
        self.angle_label.setText(f"{obs.angle:.0f}°" if obs.angle is not None else "—°")
        self.range_bar.setValue(round(obs.progress * 100))
        self.range_label.setText(f"Movement depth  ·  {obs.progress:.0%}" if obs.angle is not None else "Movement depth  ·  unavailable")
        self.canvas.highlight = getattr(self.coach.counter.exercise, self.coach.locked_side or "left")
        if obs.angle is not None and self.workout.state == "active":
            self.cue_detail.setText(obs.detail + f"  Visibility: {obs.confidence:.0%} · {obs.side}.")

    def _update_metrics(self, now):
        work = self.workout
        self.total_metric.value.setText(str(work.total_reps).zfill(2))
        self.time_metric.value.setText(self._duration(work.active_seconds))
        self.set_metric.value.setText(f"{work.set_number} / {work.sets}")
        self.set_metric.subtitle.setText(f"{work.target} reps per set")
        self.ring.set_values(work.current_reps, work.target)
        self.phase_label.setText(work.state.upper())
        self.skip_button.setVisible(work.state == "rest")
        self.pause_button.setText("Resume" if work.state == "paused" else "Pause")
        if work.state == "countdown":
            self.canvas.overlay = f"Get ready  ·  {max(1, ceil(work.deadline - now))}"
        elif work.state == "rest":
            self.canvas.overlay = f"Breathe. Recover.  ·  {max(0, ceil(work.deadline - now))}s rest"
            self.cue_title.setText("Set complete. Take a breath.")
            self.cue_detail.setText(f"Next up: set {work.set_number + 1} of {work.sets}. Counting is paused during rest.")
        elif work.state == "paused":
            self.canvas.overlay = "Session paused  ·  Space to resume"
            self.cue_title.setText("Take your time.")
            self.cue_detail.setText("Counting is paused. Resume when you're ready.")
        elif work.state == "complete":
            self.canvas.overlay = f"Session finished  ·  {work.total_reps} repetitions"
        else:
            self.canvas.overlay = ""
        self.canvas.update()

    def toggle_pause(self):
        if not self.workout or self.pending:
            return
        now = time.monotonic()
        if self.workout.state == "paused":
            self.workout.resume(now)
        else:
            self.workout.pause(now)
        self.coach.interrupt()
        if self.worker:
            self.worker.pause_video(self.workout.state != "active")
        self._update_metrics(now)

    def skip_rest(self):
        if self.workout and self.workout.skip_rest(time.monotonic()) == "new_set":
            self.coach.new_set()
            self.chart.clear()
            self._say(f"Set {self.workout.set_number}.")

    def finish_session(self):
        if not self.workout:
            return
        was_pending = self.pending
        self.pending = False
        self.workout.finish(time.monotonic())
        self.coach.interrupt()
        if self.worker:
            self.worker.requestInterruption()
        self.pause_button.setEnabled(False)
        self.end_button.setEnabled(False)
        self._update_metrics(time.monotonic())
        self.cue_title.setText("That's your session. Well done.")
        save_failed = False
        if self.canvas.is_demo:
            self.cue_detail.setText("Demo complete. Simulated repetitions are not saved to your activity.")
        elif not self.saved and not was_pending:
            self.session_settings["completed_target"] = self.workout.total_reps >= self.workout.target * self.workout.sets
            try:
                self.history.save(self.started, self.coach.key, self.source_kind, self.workout, self.session_settings)
                self.saved = True
                self.cue_detail.setText("Saved to Activity. Review your sets or export your session history as CSV.")
            except Exception as exc:
                save_failed = True
                self.cue_title.setText("Session complete · save needs attention")
                self.cue_detail.setText(f"Could not save: {exc}")
        elif was_pending:
            self.cue_detail.setText("Session cancelled before tracking started. No activity was saved.")
        if self.worker is None:
            self._lock_setup(False)
        if save_failed:
            self.end_button.setText("Retry save")
            self.end_button.setEnabled(True)
        self._refresh_history()
        self._say("Session complete.")
        self._save_preferences()

    def _source_error(self, message):
        was_pending = self.pending
        if self.workout and not was_pending:
            self.finish_session()
        else:
            self.pending = False
            if self.workout:
                self.workout.state = "complete"
        self.cue_title.setText("Let's check the input source.")
        self.cue_detail.setText(message)
        self.canvas.overlay = "Source unavailable  ·  check setup and try again"
        self.canvas.update()
        self.statusBar().showMessage(message)

    def _video_ended(self):
        if self.workout and self.workout.state != "complete":
            self.finish_session()
            self.cue_title.setText("Video analysis finished")

    def _worker_finished(self):
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
        if self.closing:
            self.close()
        elif not self._busy():
            self._lock_setup(False)
        elif self.workout:
            self.finish_session()

    @staticmethod
    def _duration(seconds):
        seconds = int(seconds)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _refresh_history(self):
        try:
            self.history_rows = self.history.rows()
        except Exception as exc:
            self.statusBar().showMessage(f"History unavailable: {exc}")
            return
        self.table.setRowCount(len(self.history_rows))
        for index, row in enumerate(self.history_rows):
            date = datetime.fromisoformat(row["started"]).strftime("%d %b %Y  ·  %H:%M")
            values = [date, EXERCISES[row["exercise"]].title, row["source"], str(row["reps"]), str(row["completed_sets"]), self._duration(row["seconds"])]
            for col, value in enumerate(values):
                self.table.setItem(index, col, QTableWidgetItem(value))
            self.table.setRowHeight(index, 52)
        self.history_empty.setVisible(not self.history_rows)
        self.export_button.setEnabled(bool(self.history_rows))
        self.history_count.value.setText(str(len(self.history_rows)))
        self.history_reps.value.setText(str(sum(row["reps"] for row in self.history_rows)))
        self.history_minutes.value.setText(f"{sum(row['seconds'] for row in self.history_rows) / 60:.1f}")

    def _history_detail(self):
        index = self.table.currentRow()
        if index < 0 or index >= len(self.history_rows):
            return
        record = self.history_rows[index]
        data = json.loads(record["payload"])
        settings = data["settings"]
        rows = "".join(f"<tr><td>{rep['set']}</td><td>{rep['rep']}</td><td>{rep['side']}</td><td>{rep['duration'] if rep['duration'] is not None else '—'} s</td></tr>" for rep in data["repetitions"])
        self.history_detail.setHtml(f"<h3>{EXERCISES[record['exercise']].title} · session #{record['id']}</h3>"
            f"<p>Target: {settings['sets']} × {settings['target']} · Rest: {settings['rest_seconds']}s · Endpoints: {settings['bent_endpoint']}° / {settings['extended_endpoint']}°</p>"
            f"<table width='100%' cellspacing='6'><tr><th align='left'>Set</th><th align='left'>Rep</th><th align='left'>Side</th><th align='left'>Rep time</th></tr>{rows}</table>")

    def export_history(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export workout history", "gym-helper-history.csv", "CSV files (*.csv)")
        if path:
            try:
                self.history.export(path)
                self.statusBar().showMessage(f"History exported to {path}", 10000)
            except Exception as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def _shortcuts(self):
        for key, action in (("Space", self.toggle_pause), ("Escape", self._finish_shortcut),
                ("Ctrl+1", lambda: self._page(0)), ("Ctrl+2", lambda: self._page(1)), ("Ctrl+3", lambda: self._page(2))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)

    def _finish_shortcut(self):
        if self._busy():
            self.finish_session()

    def _save_preferences(self):
        for name, value in (("sets", self.sets_spin.value()), ("reps", self.reps_spin.value()), ("rest", self.rest_spin.value()),
                ("camera", self.camera_spin.value()), ("side", self.side_combo.currentIndex()),
                ("mirror", self.mirror_check.isChecked()), ("skeleton", self.skeleton_check.isChecked())):
            self.settings.setValue(name, value)
        self.settings.sync()

    def _restore(self):
        for name, control in (("sets", self.sets_spin), ("reps", self.reps_spin), ("rest", self.rest_spin), ("camera", self.camera_spin)):
            if self.settings.contains(name):
                control.setValue(self.settings.value(name, type=int))
        if self.settings.contains("side"):
            self.side_combo.setCurrentIndex(max(0, min(2, self.settings.value("side", type=int))))
        for name, control in (("mirror", self.mirror_check), ("skeleton", self.skeleton_check)):
            if self.settings.contains(name):
                control.setChecked(self.settings.value(name, type=bool))

    def closeEvent(self, event):
        self._save_preferences()
        if self._busy():
            self.finish_session()
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.worker.requestInterruption()
            self.canvas.overlay = "Releasing the camera…"
            self.canvas.update()
            event.ignore()
            return
        event.accept()
