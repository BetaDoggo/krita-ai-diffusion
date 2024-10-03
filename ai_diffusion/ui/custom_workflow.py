from functools import wraps
from pathlib import Path
from typing import Any, Callable

from PyQt5.QtCore import Qt, pyqtSignal, QMetaObject, QUuid, QUrl
from PyQt5.QtGui import QFontMetrics, QIcon, QDesktopServices
from PyQt5.QtWidgets import QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout
from PyQt5.QtWidgets import QLabel, QLineEdit, QListWidgetItem, QMessageBox, QSpinBox
from PyQt5.QtWidgets import QToolButton, QVBoxLayout, QWidget, QSlider, QDoubleSpinBox

from ..custom_workflow import CustomParam, ParamKind, SortedWorkflows, WorkflowSource
from ..jobs import JobKind
from ..model import Model
from ..properties import Binding, Bind, bind, bind_combo
from ..root import root
from ..localization import translate as _
from ..util import ensure
from .generation import GenerateButton, ProgressBar, QueueButton, HistoryWidget, create_error_label
from .switch import SwitchWidget
from .widget import TextPromptWidget, WorkspaceSelectWidget
from . import theme


class LayerSelect(QComboBox):
    value_changed = pyqtSignal()

    def __init__(self, filter: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.filter = filter
        self.currentIndexChanged.connect(lambda _: self.value_changed.emit())

        self._update()
        root.active_model.layers.changed.connect(self._update)

    def _update(self):
        if self.filter is None:
            layers = root.active_model.layers.all
        elif self.filter == "image":
            layers = root.active_model.layers.images
        elif self.filter == "mask":
            layers = root.active_model.layers.masks
        else:
            assert False, f"Unknown filter: {self.filter}"

        for l in layers:
            if self.findData(l.id) == -1:
                self.addItem(l.name, l.id)
        i = 0
        while i < self.count():
            if self.itemData(i) not in (l.id for l in layers):
                self.removeItem(i)
            else:
                i += 1

    @property
    def value(self) -> str:
        if self.currentIndex() == -1:
            return ""
        return self.currentData().toString()

    @value.setter
    def value(self, value: str):
        i = self.findData(QUuid(value))
        if i != -1 and i != self.currentIndex():
            self.setCurrentIndex(i)


class IntParamWidget(QWidget):
    value_changed = pyqtSignal()

    def __init__(self, param: CustomParam, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        assert param.min is not None and param.max is not None and param.default is not None
        if param.max - param.min <= 200:
            self._widget = QSlider(Qt.Orientation.Horizontal, parent)
            self._widget.setRange(int(param.min), int(param.max))
            self._widget.setMinimumHeight(self._widget.minimumSizeHint().height() + 4)
            self._widget.valueChanged.connect(self._notify)
            self._label = QLabel(self)
            self._label.setFixedWidth(40)
            self._label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(self._widget)
            layout.addWidget(self._label)
        else:
            self._widget = QSpinBox(parent)
            self._widget.setRange(int(param.min), int(param.max))
            self._widget.valueChanged.connect(self._notify)
            self._label = None
            layout = QHBoxLayout(self)
            layout.addWidget(self._widget)

        self.value = param.default

    def _notify(self):
        if self._label:
            self._label.setText(str(self._widget.value()))
        self.value_changed.emit()

    @property
    def value(self):
        return self._widget.value()

    @value.setter
    def value(self, value: int):
        self._widget.setValue(value)


class FloatParamWidget(QWidget):
    value_changed = pyqtSignal()

    def __init__(self, param: CustomParam, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        assert param.min is not None and param.max is not None and param.default is not None
        if param.max - param.min <= 20:
            self._widget = QSlider(Qt.Orientation.Horizontal, parent)
            self._widget.setRange(round(param.min * 100), round(param.max * 100))
            self._widget.setMinimumHeight(self._widget.minimumSizeHint().height() + 4)
            self._widget.valueChanged.connect(self._notify)
            self._label = QLabel(self)
            self._label.setFixedWidth(40)
            self._label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(self._widget)
            layout.addWidget(self._label)
        else:
            self._widget = QDoubleSpinBox(parent)
            self._widget.setRange(param.min, param.max)
            self._widget.valueChanged.connect(self._notify)
            self._label = None
            layout = QHBoxLayout(self)
            layout.addWidget(self._widget)

        self.value = param.default

    def _notify(self):
        if self._label:
            self._label.setText(f"{self.value:.2f}")
        self.value_changed.emit()

    @property
    def value(self):
        if isinstance(self._widget, QSlider):
            return self._widget.value() / 100
        else:
            return self._widget.value()

    @value.setter
    def value(self, value: float):
        if isinstance(self._widget, QSlider):
            self._widget.setValue(round(value * 100))
        else:
            self._widget.setValue(value)


class BoolParamWidget(QWidget):
    value_changed = pyqtSignal()

    _true_text = _("On")
    _false_text = _("Off")

    def __init__(self, param: CustomParam, parent: QWidget | None = None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        fm = QFontMetrics(self.font())
        self._label = QLabel(self)
        self._label.setMinimumWidth(max(fm.width(self._true_text), fm.width(self._false_text)) + 4)
        self._widget = SwitchWidget(parent)
        self._widget.toggled.connect(self._notify)
        layout.addWidget(self._widget)
        layout.addWidget(self._label)

        assert isinstance(param.default, bool)
        self.value = param.default

    def _notify(self):
        self._label.setText(self._true_text if self.value else self._false_text)
        self.value_changed.emit()

    @property
    def value(self):
        return self._widget.isChecked()

    @value.setter
    def value(self, value: bool):
        self._widget.setChecked(value)


class TextParamWidget(QLineEdit):
    value_changed = pyqtSignal()

    def __init__(self, param: CustomParam, parent: QWidget | None = None):
        super().__init__(parent)
        assert isinstance(param.default, str)

        self.value = param.default
        self.textChanged.connect(self._notify)

    def _notify(self):
        self.value_changed.emit()

    @property
    def value(self):
        return self.text()

    @value.setter
    def value(self, value: str):
        self.setText(value)


class PromptParamWidget(TextPromptWidget):
    value_changed = pyqtSignal()

    def __init__(self, param: CustomParam, parent: QWidget | None = None):
        super().__init__(is_negative=param.kind is ParamKind.prompt_negative, parent=parent)
        assert isinstance(param.default, str)

        self.setObjectName("PromptParam")
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame#PromptParam {{ background-color: {theme.base}; border: 1px solid {theme.line_base}; }}"
        )
        self.text = param.default
        self.text_changed.connect(self.value_changed)

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, value: str):
        self.text = value


CustomParamWidget = (
    LayerSelect
    | IntParamWidget
    | FloatParamWidget
    | BoolParamWidget
    | TextParamWidget
    | PromptParamWidget
)


def _create_param_widget(param: CustomParam, parent: QWidget):
    if param.kind is ParamKind.image_layer:
        return LayerSelect("image", parent)
    if param.kind is ParamKind.mask_layer:
        return LayerSelect("mask", parent)
    if param.kind is ParamKind.number_int:
        return IntParamWidget(param, parent)
    if param.kind is ParamKind.number_float:
        return FloatParamWidget(param, parent)
    if param.kind is ParamKind.boolean:
        return BoolParamWidget(param, parent)
    if param.kind is ParamKind.text:
        return TextParamWidget(param, parent)
    if param.kind in [ParamKind.prompt_positive, ParamKind.prompt_negative]:
        return PromptParamWidget(param, parent)
    assert False, f"Unknown param kind: {param.kind}"


class WorkflowParamsWidget(QWidget):
    value_changed = pyqtSignal()

    def __init__(self, params: list[CustomParam], parent: QWidget | None = None):
        super().__init__(parent)
        self._widgets: dict[str, CustomParamWidget] = {}

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnMinimumWidth(1, 10)
        self.setLayout(layout)

        for p in params:
            label = QLabel(p.name, self)
            widget = _create_param_widget(p, self)
            widget.value_changed.connect(self._notify)
            row = len(self._widgets)
            layout.addWidget(label, row, 0)
            layout.addWidget(widget, row, 2)
            self._widgets[p.name] = widget

    def _notify(self):
        self.value_changed.emit()

    @property
    def value(self):
        return {name: widget.value for name, widget in self._widgets.items()}

    @value.setter
    def value(self, values: dict[str, Any]):
        for name, value in values.items():
            if widget := self._widgets.get(name):
                if type(widget.value) == type(value):
                    widget.value = value


def popup_on_error(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            QMessageBox.critical(self, _("Error"), str(e))

    return wrapper


def _create_tool_button(parent: QWidget, icon: QIcon, tooltip: str, handler: Callable[..., None]):
    button = QToolButton(parent)
    button.setIcon(icon)
    button.setToolTip(tooltip)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setAutoRaise(True)
    button.clicked.connect(handler)
    return button


class CustomWorkflowWidget(QWidget):
    def __init__(self):
        super().__init__()

        self._model = root.active_model
        self._model_bindings: list[QMetaObject.Connection | Binding] = []

        self._workspace_select = WorkspaceSelectWidget(self)

        self._workflow_select_widgets = QWidget(self)

        self._workflow_select = QComboBox(self._workflow_select_widgets)
        self._workflow_select.setModel(SortedWorkflows(root.workflows))
        self._workflow_select.currentIndexChanged.connect(self._change_workflow)

        self._import_workflow_button = _create_tool_button(
            self._workflow_select_widgets,
            theme.icon("import"),
            _("Import workflow from file"),
            self._import_workflow,
        )
        self._save_workflow_button = _create_tool_button(
            self._workflow_select_widgets,
            theme.icon("save"),
            _("Save workflow to file"),
            self._save_workflow,
        )
        self._delete_workflow_button = _create_tool_button(
            self._workflow_select_widgets,
            theme.icon("discard"),
            _("Delete the currently selected workflow"),
            self._delete_workflow,
        )
        self._open_webui_button = _create_tool_button(
            self._workflow_select_widgets,
            theme.icon("comfyui"),
            _("Open Web UI to create custom workflows"),
            self._open_webui,
        )

        self._workflow_edit_widgets = QWidget(self)
        self._workflow_edit_widgets.setVisible(False)

        self._workflow_name_edit = QLineEdit(self._workflow_edit_widgets)
        self._workflow_name_edit.textEdited.connect(self._edit_name)
        self._workflow_name_edit.returnPressed.connect(self._accept_name)

        self._accept_name_button = _create_tool_button(
            self._workflow_edit_widgets, theme.icon("apply"), _("Apply"), self._accept_name
        )
        self._cancel_name_button = _create_tool_button(
            self._workflow_edit_widgets, theme.icon("cancel"), _("Cancel"), self._cancel_name
        )

        self._params_widget = WorkflowParamsWidget([], self)

        self._generate_button = GenerateButton(JobKind.diffusion, self)
        self._queue_button = QueueButton(parent=self)
        self._queue_button.setFixedHeight(self._generate_button.height() - 2)
        self._progress_bar = ProgressBar(self)
        self._error_text = create_error_label(self)

        self._history = HistoryWidget(self)
        self._history.item_activated.connect(self.apply_result)

        self._layout = QVBoxLayout()
        select_layout = QHBoxLayout()
        select_layout.setContentsMargins(0, 0, 0, 0)
        select_layout.setSpacing(2)
        select_layout.addWidget(self._workflow_select)
        select_layout.addWidget(self._import_workflow_button)
        select_layout.addWidget(self._save_workflow_button)
        select_layout.addWidget(self._delete_workflow_button)
        select_layout.addWidget(self._open_webui_button)
        self._workflow_select_widgets.setLayout(select_layout)
        edit_layout = QHBoxLayout()
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(2)
        edit_layout.addWidget(self._workflow_name_edit)
        edit_layout.addWidget(self._accept_name_button)
        edit_layout.addWidget(self._cancel_name_button)
        self._workflow_edit_widgets.setLayout(edit_layout)
        header_layout = QHBoxLayout()
        header_layout.addWidget(self._workspace_select)
        header_layout.addWidget(self._workflow_select_widgets)
        header_layout.addWidget(self._workflow_edit_widgets)
        self._layout.addLayout(header_layout)
        self._layout.addWidget(self._params_widget)
        actions_layout = QHBoxLayout()
        actions_layout.addWidget(self._generate_button)
        actions_layout.addWidget(self._queue_button)
        self._layout.addLayout(actions_layout)
        self._layout.addWidget(self._progress_bar)
        self._layout.addWidget(self._error_text)
        self._layout.addWidget(self._history)
        self.setLayout(self._layout)

    def _update_current_workflow(self):
        if not self.model.custom.workflow:
            self._save_workflow_button.setEnabled(False)
            self._delete_workflow_button.setEnabled(False)
            return
        self._save_workflow_button.setEnabled(True)
        self._delete_workflow_button.setEnabled(
            self.model.custom.workflow.source is WorkflowSource.local
        )

        self._params_widget.deleteLater()
        self._params_widget = WorkflowParamsWidget(self.model.custom.metadata, self)
        self._params_widget.value = self.model.custom.params
        self._layout.insertWidget(1, self._params_widget)
        self._params_widget.value_changed.connect(self._change_params)

    def _change_workflow(self):
        self.model.custom.workflow_id = self._workflow_select.currentData()

    def _change_params(self):
        self.model.custom.params = self._params_widget.value

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, model: Model):
        if self._model != model:
            Binding.disconnect_all(self._model_bindings)
            self._model = model
            self._model_bindings = [
                bind(model, "workspace", self._workspace_select, "value", Bind.one_way),
                bind_combo(model.custom, "workflow_id", self._workflow_select, Bind.one_way),
                model.workspace_changed.connect(self._cancel_name),
                model.custom.graph_changed.connect(self._update_current_workflow),
                model.error_changed.connect(self._error_text.setText),
                model.has_error_changed.connect(self._error_text.setVisible),
                self._generate_button.clicked.connect(model.generate_custom),
            ]
            self._queue_button.model = model
            self._progress_bar.model = model
            self._history.model_ = model
            self._update_current_workflow()

    def apply_result(self, item: QListWidgetItem):
        job_id, index = self._history.item_info(item)
        self.model.apply_generated_result(job_id, index)

    @popup_on_error
    def _import_workflow(self, *args):
        filename, __ = QFileDialog.getOpenFileName(
            self,
            _("Import Workflow"),
            str(Path.home()),
            "Workflow Files (*.json);;All Files (*)",
        )
        if filename:
            self.model.custom.import_file(Path(filename))

    def _save_workflow(self):
        self.is_edit_mode = True

    def _delete_workflow(self):
        filepath = ensure(self.model.custom.workflow).path
        q = QMessageBox.question(
            self,
            _("Delete Workflow"),
            _("Are you sure you want to delete the current workflow?") + f"\n{filepath}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.StandardButton.No,
        )
        if q == QMessageBox.StandardButton.Yes:
            self.model.custom.remove_workflow()

    def _open_webui(self):
        if client := root.connection.client_if_connected:
            QDesktopServices.openUrl(QUrl(client.url))

    @property
    def is_edit_mode(self):
        return self._workflow_edit_widgets.isVisible()

    @is_edit_mode.setter
    def is_edit_mode(self, value: bool):
        if value == self.is_edit_mode:
            return
        self._workflow_select_widgets.setVisible(not value)
        self._workflow_edit_widgets.setVisible(value)
        if value:
            self._workflow_name_edit.setText(self.model.custom.workflow_id)
            self._workflow_name_edit.selectAll()
            self._workflow_name_edit.setFocus()

    def _edit_name(self):
        self._accept_name_button.setEnabled(self._workflow_name_edit.text().strip() != "")

    @popup_on_error
    def _accept_name(self, *args):
        self.model.custom.save_as(self._workflow_name_edit.text())
        self.is_edit_mode = False

    def _cancel_name(self):
        self.is_edit_mode = False
