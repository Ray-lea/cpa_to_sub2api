from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QSizePolicy,
)

from app.converter import (
    ConversionError,
    ExportSettings,
    ProxyConfig,
    SourceRecord,
    collect_json_files_from_folder,
    export_to_file,
    generate_default_filename,
    merge_source_records,
    refresh_target_names,
    validate_output_filename,
)


HEADER_FONT_FAMILY = "Microsoft YaHei UI"
BODY_FONT_FAMILY = "Segoe UI"


class ExportSettingsDialog(QDialog):
    def __init__(self, output_dir: Path, settings: ExportSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected_output_dir = output_dir
        self.selected_settings = settings

        self.setWindowTitle("导出设置")
        self.resize(780, 760)
        self.setMinimumSize(700, 620)
        self._build_ui(output_dir, settings)
        self._apply_styles()
        self._update_proxy_fields()

    def _build_ui(self, output_dir: Path, settings: ExportSettings) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        intro = QLabel("完整导出配置放在这里编辑。保存后，主界面只保留摘要。")
        intro.setObjectName("DialogIntro")
        root_layout.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        root_layout.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(16)

        basic_box = QGroupBox("基础设置")
        basic_layout = QFormLayout(basic_box)
        basic_layout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        basic_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        basic_layout.setHorizontalSpacing(14)
        basic_layout.setVerticalSpacing(14)

        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(10)
        self.output_dir_edit = QLineEdit(str(output_dir))
        self.output_dir_button = QPushButton("选择目录")
        self.output_dir_button.setFixedWidth(108)
        output_row.addWidget(self.output_dir_edit, 1)
        output_row.addWidget(self.output_dir_button)
        output_widget = QWidget()
        output_widget.setLayout(output_row)
        basic_layout.addRow("输出目录", output_widget)

        self.output_file_edit = QLineEdit(settings.output_filename)
        basic_layout.addRow("输出文件名", self.output_file_edit)

        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(0, 9999)
        self.concurrency_spin.setValue(settings.concurrency)
        basic_layout.addRow("并发数", self.concurrency_spin)

        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(0, 9999)
        self.priority_spin.setValue(settings.priority)
        basic_layout.addRow("优先级", self.priority_spin)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setDecimals(2)
        self.rate_spin.setRange(0, 9999)
        self.rate_spin.setSingleStep(0.1)
        self.rate_spin.setValue(settings.rate_multiplier)
        basic_layout.addRow("倍率", self.rate_spin)

        self.auto_pause_checkbox = QCheckBox("到期后自动暂停")
        self.auto_pause_checkbox.setChecked(settings.auto_pause_on_expired)
        basic_layout.addRow("账号策略", self.auto_pause_checkbox)
        content_layout.addWidget(basic_box)

        proxy_box = QGroupBox("代理设置")
        proxy_layout = QGridLayout(proxy_box)
        proxy_layout.setHorizontalSpacing(12)
        proxy_layout.setVerticalSpacing(12)
        proxy_layout.setColumnStretch(1, 1)

        self.proxy_enabled_checkbox = QCheckBox("启用代理")
        self.proxy_enabled_checkbox.setChecked(settings.proxy.enabled)
        self.proxy_name_edit = QLineEdit(settings.proxy.name)
        self.proxy_protocol_combo = QComboBox()
        self.proxy_protocol_combo.addItems(["http", "https", "socks5", "socks5h"])
        self.proxy_protocol_combo.setCurrentText(settings.proxy.protocol)
        self.proxy_host_edit = QLineEdit(settings.proxy.host)
        self.proxy_port_spin = QSpinBox()
        self.proxy_port_spin.setRange(1, 65535)
        self.proxy_port_spin.setValue(settings.proxy.port)
        self.proxy_username_edit = QLineEdit(settings.proxy.username)
        self.proxy_password_edit = QLineEdit(settings.proxy.password)
        self.proxy_password_edit.setEchoMode(QLineEdit.Password)
        self.proxy_status_combo = QComboBox()
        self.proxy_status_combo.addItems(["active", "inactive"])
        self.proxy_status_combo.setCurrentText(settings.proxy.status)

        proxy_layout.addWidget(self.proxy_enabled_checkbox, 0, 0, 1, 2)
        proxy_layout.addWidget(QLabel("名称"), 1, 0)
        proxy_layout.addWidget(self.proxy_name_edit, 1, 1)
        proxy_layout.addWidget(QLabel("协议"), 2, 0)
        proxy_layout.addWidget(self.proxy_protocol_combo, 2, 1)
        proxy_layout.addWidget(QLabel("地址"), 3, 0)
        proxy_layout.addWidget(self.proxy_host_edit, 3, 1)
        proxy_layout.addWidget(QLabel("端口"), 4, 0)
        proxy_layout.addWidget(self.proxy_port_spin, 4, 1)
        proxy_layout.addWidget(QLabel("用户名"), 5, 0)
        proxy_layout.addWidget(self.proxy_username_edit, 5, 1)
        proxy_layout.addWidget(QLabel("密码"), 6, 0)
        proxy_layout.addWidget(self.proxy_password_edit, 6, 1)
        proxy_layout.addWidget(QLabel("状态"), 7, 0)
        proxy_layout.addWidget(self.proxy_status_combo, 7, 1)
        content_layout.addWidget(proxy_box)
        content_layout.addStretch(1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("PrimaryButton")
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.save_button)
        root_layout.addLayout(button_row)

        self.output_dir_button.clicked.connect(self._choose_output_dir)
        self.proxy_enabled_checkbox.toggled.connect(self._update_proxy_fields)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.accept)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f4f7fb;
            }
            QLabel#DialogIntro {
                color: #5b6b82;
                padding: 0 4px 4px 4px;
            }
            QGroupBox {
                margin-top: 10px;
                border: 1px solid #d9e2ef;
                border-radius: 14px;
                padding: 14px 12px 12px 12px;
                font-weight: 700;
                color: #24426b;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                min-height: 40px;
                background: #fbfdff;
                border: 1px solid #cfd9e8;
                border-radius: 10px;
                padding: 6px 10px;
            }
            QPushButton {
                min-height: 40px;
                padding: 0 16px;
                border-radius: 10px;
                border: 1px solid #c8d5e6;
                background: #f7fafc;
            }
            QPushButton#PrimaryButton {
                background: #1e64d6;
                border-color: #1e64d6;
                color: #ffffff;
                font-weight: 700;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            self.output_dir_edit.text().strip() or str(Path.cwd()),
        )
        if folder:
            self.output_dir_edit.setText(folder)

    def _update_proxy_fields(self) -> None:
        enabled = self.proxy_enabled_checkbox.isChecked()
        for widget in [
            self.proxy_name_edit,
            self.proxy_protocol_combo,
            self.proxy_host_edit,
            self.proxy_port_spin,
            self.proxy_username_edit,
            self.proxy_password_edit,
            self.proxy_status_combo,
        ]:
            widget.setEnabled(enabled)

    def accept(self) -> None:
        try:
            output_dir = Path(self.output_dir_edit.text().strip())
            if not str(output_dir).strip():
                raise ConversionError("输出目录不能为空。")
            settings = ExportSettings(
                output_filename=validate_output_filename(self.output_file_edit.text()),
                concurrency=int(self.concurrency_spin.value()),
                priority=int(self.priority_spin.value()),
                rate_multiplier=float(self.rate_spin.value()),
                auto_pause_on_expired=self.auto_pause_checkbox.isChecked(),
                proxy=ProxyConfig(
                    enabled=self.proxy_enabled_checkbox.isChecked(),
                    name=self.proxy_name_edit.text().strip() or "批量导入代理",
                    protocol=self.proxy_protocol_combo.currentText(),
                    host=self.proxy_host_edit.text().strip(),
                    port=int(self.proxy_port_spin.value()),
                    username=self.proxy_username_edit.text().strip(),
                    password=self.proxy_password_edit.text(),
                    status=self.proxy_status_combo.currentText(),
                ),
            )
            settings.validate()
        except ConversionError as exc:
            QMessageBox.critical(self, "错误", str(exc))
            return

        self.selected_output_dir = output_dir
        self.selected_settings = settings
        super().accept()


class ConverterMainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[SourceRecord] = []
        self.last_output_path: Path | None = None
        self._table_updating = False
        self.output_dir = Path.cwd()
        self.export_settings = ExportSettings(output_filename=generate_default_filename())

        self.setWindowTitle("Sub2API 批量转换器")
        self.resize(1440, 940)
        self.setMinimumSize(1200, 820)

        self._build_ui()
        self._apply_styles()
        self._refresh_table()
        self._refresh_settings_summary()

    def _build_ui(self) -> None:
        container = QWidget()
        self.setCentralWidget(container)
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(16)

        header_layout = QVBoxLayout()
        title = QLabel("OpenAI 账号 JSON 批量转换")
        title_font = QFont(HEADER_FONT_FAMILY, 18)
        title_font.setBold(True)
        title.setFont(title_font)
        subtitle = QLabel("批量载入源文件，筛选需要的账号，统一导出成一个目标 JSON。")
        subtitle.setObjectName("Subtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root_layout.addLayout(header_layout)

        file_card = self._create_card("文件区")
        file_layout = file_card.layout()
        button_row = QHBoxLayout()
        self.add_files_button = QPushButton("添加文件")
        self.add_folder_button = QPushButton("添加文件夹")
        self.clear_button = QPushButton("清空")
        self.file_summary_label = QLabel("尚未载入文件。")
        self.file_summary_label.setObjectName("SummaryLabel")

        button_row.addWidget(self.add_files_button)
        button_row.addWidget(self.add_folder_button)
        button_row.addWidget(self.clear_button)
        button_row.addSpacing(8)
        button_row.addWidget(self.file_summary_label, 1)
        file_layout.addLayout(button_row)
        root_layout.addWidget(file_card)

        table_card = self._create_card("文件列表")
        table_layout = table_card.layout()
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["选择", "文件名", "邮箱", "目标名称", "套餐", "源格式", "校验结果"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        table_layout.addWidget(self.table)
        root_layout.addWidget(table_card, 1)

        lower_splitter = QSplitter(Qt.Horizontal)
        lower_splitter.setChildrenCollapsible(False)

        action_card = self._create_card("导出操作")
        action_card.setMinimumWidth(420)
        action_layout = action_card.layout()
        action_summary = QWidget()
        action_summary_layout = QGridLayout(action_summary)
        action_summary_layout.setContentsMargins(0, 0, 0, 0)
        action_summary_layout.setHorizontalSpacing(14)
        action_summary_layout.setVerticalSpacing(12)
        self.summary_output_dir = QLabel()
        self.summary_output_dir.setObjectName("ValueLabel")
        self.summary_output_file = QLabel()
        self.summary_output_file.setObjectName("ValueLabel")
        self.summary_proxy = QLabel()
        self.summary_proxy.setObjectName("ValueLabel")
        self.summary_policy = QLabel()
        self.summary_policy.setObjectName("ValueLabel")
        action_summary_layout.addWidget(QLabel("输出目录"), 0, 0)
        action_summary_layout.addWidget(self.summary_output_dir, 0, 1)
        action_summary_layout.addWidget(QLabel("输出文件"), 1, 0)
        action_summary_layout.addWidget(self.summary_output_file, 1, 1)
        action_summary_layout.addWidget(QLabel("代理"), 2, 0)
        action_summary_layout.addWidget(self.summary_proxy, 2, 1)
        action_summary_layout.addWidget(QLabel("导出参数"), 3, 0)
        action_summary_layout.addWidget(self.summary_policy, 3, 1)
        action_summary_layout.setColumnStretch(1, 1)
        action_layout.addWidget(action_summary)

        helper_label = QLabel("完整配置已移到独立窗口编辑，主界面只保留摘要，避免挤压。")
        helper_label.setObjectName("Subtitle")
        action_layout.addWidget(helper_label)

        action_buttons = QHBoxLayout()
        self.edit_settings_button = QPushButton("编辑导出设置")
        self.convert_button = QPushButton("开始转换")
        self.convert_button.setObjectName("PrimaryButton")
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setEnabled(False)
        action_buttons.addWidget(self.edit_settings_button)
        action_buttons.addWidget(self.convert_button)
        action_buttons.addWidget(self.open_output_button)
        action_buttons.addStretch(1)
        action_layout.addLayout(action_buttons)

        result_card = self._create_card("执行结果")
        result_card.setMinimumWidth(420)
        result_layout = result_card.layout()
        self.result_summary_label = QLabel("成功 0 个，失败 0 个。")
        self.result_summary_label.setObjectName("SummaryLabel")
        self.result_path_edit = QLineEdit()
        self.result_path_edit.setReadOnly(True)
        self.result_log_edit = QPlainTextEdit()
        self.result_log_edit.setReadOnly(True)
        self.result_log_edit.setPlaceholderText("这里会显示导出结果、无效文件和错误原因。")
        result_layout.addWidget(self.result_summary_label)
        result_layout.addWidget(self.result_path_edit)
        result_layout.addWidget(self.result_log_edit, 1)

        lower_splitter.addWidget(action_card)
        lower_splitter.addWidget(result_card)
        lower_splitter.setStretchFactor(0, 4)
        lower_splitter.setStretchFactor(1, 5)
        lower_splitter.setSizes([520, 680])
        root_layout.addWidget(lower_splitter, 0)

        self.add_files_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.clear_button.clicked.connect(self._clear_records)
        self.edit_settings_button.clicked.connect(self._edit_settings)
        self.convert_button.clicked.connect(self._convert_selected)
        self.open_output_button.clicked.connect(self._open_output_directory)
        self.table.itemChanged.connect(self._handle_table_item_changed)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f4f7fb;
            }
            QWidget {
                font-family: "Segoe UI";
                font-size: 13px;
                color: #1f2a37;
            }
            QLabel#Subtitle {
                color: #5b6b82;
                font-size: 13px;
            }
            QLabel#SummaryLabel {
                color: #24426b;
                font-weight: 600;
            }
            QLabel#ValueLabel {
                color: #16385f;
                font-weight: 600;
                background: #f5f9ff;
                border: 1px solid #d8e3f0;
                border-radius: 10px;
                padding: 10px 12px;
            }
            QFrame#Card {
                background: #ffffff;
                border: 1px solid #d9e2ef;
                border-radius: 18px;
            }
            QSplitter::handle {
                background: #d9e2ef;
            }
            QSplitter::handle:horizontal {
                width: 8px;
            }
            QLabel#CardTitle {
                font-family: "Microsoft YaHei UI";
                font-size: 15px;
                font-weight: 700;
                color: #123258;
            }
            QPushButton {
                min-height: 38px;
                padding: 0 16px;
                border-radius: 10px;
                border: 1px solid #c8d5e6;
                background: #f7fafc;
            }
            QPushButton:hover {
                background: #eef5ff;
            }
            QPushButton#PrimaryButton {
                background: #1e64d6;
                border-color: #1e64d6;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton#PrimaryButton:hover {
                background: #1857be;
            }
            QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background: #fbfdff;
                border: 1px solid #cfd9e8;
                border-radius: 10px;
                padding: 8px 10px;
            }
            QTableWidget {
                background: #fbfdff;
                border: 1px solid #d6e0ee;
                border-radius: 14px;
                gridline-color: #e8eef7;
                alternate-background-color: #f5f9ff;
            }
            QHeaderView::section {
                background: #eef4fb;
                border: none;
                border-bottom: 1px solid #d6e0ee;
                padding: 10px;
                font-weight: 700;
                color: #24426b;
            }
            QGroupBox {
                margin-top: 12px;
                border: 1px solid #d9e2ef;
                border-radius: 14px;
                padding: 14px 12px 12px 12px;
                font-weight: 700;
                color: #24426b;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )

    def _create_card(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        label = QLabel(title)
        label.setObjectName("CardTitle")
        layout.addWidget(label)
        return card

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择源文件",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if paths:
            self._load_paths([Path(path) for path in paths])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "选择包含源文件的文件夹",
            str(Path.cwd()),
        )
        if not folder:
            return
        try:
            paths = collect_json_files_from_folder(Path(folder))
        except ConversionError as exc:
            self._show_error(str(exc))
            return
        if not paths:
            self._append_result_message("选择的文件夹中没有找到 JSON 文件。")
            return
        self._load_paths(paths)

    def _load_paths(self, paths: list[Path]) -> None:
        self.records = merge_source_records(self.records, paths)
        self._refresh_table()
        self._append_result_message(f"已载入 {len(paths)} 个文件，当前总数 {len(self.records)}。")

    def _clear_records(self) -> None:
        self.records = []
        self.last_output_path = None
        self.result_path_edit.clear()
        self.result_log_edit.clear()
        self.open_output_button.setEnabled(False)
        self._refresh_table()

    def _handle_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._table_updating or item.column() != 0:
            return
        row = item.row()
        if row < 0 or row >= len(self.records):
            return
        record = self.records[row]
        if not record.is_valid:
            item.setCheckState(Qt.Unchecked)
            return
        record.selected = item.checkState() == Qt.Checked
        refresh_target_names(self.records)
        self._refresh_table()

    def _edit_settings(self) -> None:
        dialog = ExportSettingsDialog(self.output_dir, self.export_settings, self)
        if dialog.exec():
            self.output_dir = dialog.selected_output_dir
            self.export_settings = dialog.selected_settings
            self._refresh_settings_summary()

    def _convert_selected(self) -> None:
        try:
            self.export_settings.validate()
            output_path = export_to_file(self.records, self.export_settings, self.output_dir)
        except ConversionError as exc:
            self._show_error(str(exc))
            self._append_result_message(f"转换失败：{exc}")
            return
        except OSError as exc:
            self._show_error(f"无法写入输出文件：{exc}")
            self._append_result_message(f"转换失败：{exc}")
            return

        self.last_output_path = output_path
        self.result_path_edit.setText(str(output_path))
        self.open_output_button.setEnabled(True)
        success_count = len([record for record in self.records if record.is_valid and record.selected])
        failed_count = len([record for record in self.records if not record.is_valid])
        self.result_summary_label.setText(f"成功 {success_count} 个，失败 {failed_count} 个。")
        self._append_result_message(f"导出完成：{output_path}")
        self.export_settings = ExportSettings(
            output_filename=generate_default_filename(),
            concurrency=self.export_settings.concurrency,
            priority=self.export_settings.priority,
            rate_multiplier=self.export_settings.rate_multiplier,
            auto_pause_on_expired=self.export_settings.auto_pause_on_expired,
            proxy=self.export_settings.proxy,
        )
        self._refresh_settings_summary()

    def _open_output_directory(self) -> None:
        target = self.last_output_path.parent if self.last_output_path else self.output_dir
        if not target.exists():
            self._show_error("输出目录不存在。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _refresh_table(self) -> None:
        refresh_target_names(self.records)
        self._table_updating = True
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            self._set_checkbox_item(row, record)
            self.table.setItem(row, 1, QTableWidgetItem(record.file_name))
            self.table.setItem(row, 2, QTableWidgetItem(record.email or "-"))
            self.table.setItem(row, 3, QTableWidgetItem(record.target_name or "-"))
            self.table.setItem(row, 4, QTableWidgetItem(record.plan_type or "-"))
            self.table.setItem(row, 5, QTableWidgetItem(record.variant))
            self._set_status_item(row, record)
        self._table_updating = False
        self._update_file_summary()
        self.table.resizeRowsToContents()

    def _set_checkbox_item(self, row: int, record: SourceRecord) -> None:
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        item.setTextAlignment(Qt.AlignCenter)
        if record.is_valid:
            item.setCheckState(Qt.Checked if record.selected else Qt.Unchecked)
        else:
            item.setCheckState(Qt.Unchecked)
            item.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row, 0, item)

    def _set_status_item(self, row: int, record: SourceRecord) -> None:
        status = QTableWidgetItem(record.status_text)
        if record.is_valid:
            status.setForeground(QColor("#0f7b47"))
        else:
            status.setForeground(QColor("#b42318"))
        self.table.setItem(row, 6, status)

    def _update_file_summary(self) -> None:
        total = len(self.records)
        valid = len([record for record in self.records if record.is_valid])
        selected = len([record for record in self.records if record.is_valid and record.selected])
        invalid = len([record for record in self.records if not record.is_valid])
        self.file_summary_label.setText(
            f"共 {total} 个文件，已识别 {valid} 个，已勾选 {selected} 个，无效 {invalid} 个。"
        )
        self.result_summary_label.setText(f"成功 {selected} 个，失败 {invalid} 个。")

    def _refresh_settings_summary(self) -> None:
        proxy = self.export_settings.proxy
        proxy_text = "未启用"
        if proxy.enabled:
            proxy_text = f"{proxy.protocol}://{proxy.host}:{proxy.port}"
        self.summary_output_dir.setText(str(self.output_dir))
        self.summary_output_file.setText(self.export_settings.output_filename)
        self.summary_proxy.setText(proxy_text)
        self.summary_policy.setText(
            f"并发 {self.export_settings.concurrency} / 优先级 {self.export_settings.priority} / "
            f"倍率 {self.export_settings.rate_multiplier:.2f}"
        )

    def _append_result_message(self, message: str) -> None:
        self.result_log_edit.appendPlainText(message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "错误", message)


def build_application() -> QApplication:
    app = QApplication.instance()
    if app is not None:
        return app
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    created = QApplication([])
    created.setStyle("Fusion")
    font = QFont(BODY_FONT_FAMILY, 10)
    created.setFont(font)
    return created
