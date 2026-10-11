import QtQuick

// One config tag, sunk like the Engine Tuner fields. A short number sits beside another.
Item {
    id: field

    property var cell: null
    signal commit(int index, string text)
    signal pick(int index)
    signal browse(int index)
    signal open(int index)
    signal toggled()
    signal menu(var cell)

    property bool expanded: false
    readonly property int lineCount: cell && cell.lines > 1 ? cell.lines : 1
    visible: cell !== null && cell.name !== undefined
    implicitHeight: (lineCount > 1 ? (expanded ? tallBody.implicitHeight : 48) : 48) + (chips.visible ? 22 : 0)
    clip: true

    SunkField {
        id: well
        visible: field.lineCount === 1
        anchors.left: parent.left
        anchors.right: sideBtn.visible ? sideBtn.left : parent.right
        anchors.rightMargin: sideBtn.visible ? 6 : 0
        anchors.top: parent.top
        anchors.bottom: chips.visible ? chips.top : parent.bottom
        stacked: true
        label: field.cell ? field.cell.name : ""
        unit: field.cell && field.cell.unit ? field.cell.unit : ""
        value: field.cell && field.cell.value ? field.cell.value : ""
        onEdited: {
            if (!field.cell || field.cell.box || field.cell.editor === "menu")
                return
            field.commit(field.cell.index, text)
        }
    }

    Item {
        id: tallBody
        visible: field.lineCount > 1
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        clip: true
        Item {
            id: tallLab
            anchors.left: parent.left
            anchors.right: parent.right
            height: 16
            Text {
                anchors.left: parent.left
                anchors.right: caret.left
                anchors.verticalCenter: parent.verticalCenter
                text: field.cell ? field.cell.name : ""
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
                elide: Text.ElideRight
            }
            Text {
                id: caret
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: "\u203a"
                color: "#ff7a3c"
                font.pixelSize: 16
                rotation: field.expanded ? 90 : 0
                transformOrigin: Item.Center
                Behavior on rotation { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            }
            TapHandler { onTapped: field.toggled() }
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tallLab.bottom
            anchors.bottom: parent.bottom
            radius: 8
            clip: true
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
            Flickable {
                id: proseFlick
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                contentWidth: width
                contentHeight: proseEdit.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                TextEdit {
                    id: proseEdit
                    width: proseFlick.width
                    color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
                    font.pixelSize: 12
                    wrapMode: TextEdit.Wrap
                    selectByMouse: field.expanded
                    readOnly: !field.expanded
                    text: field.cell && field.cell.value ? field.cell.value : ""
                    onEditingFinished: {
                        if (field.cell)
                            field.commit(field.cell.index, text)
                    }
                }
            }
            TapHandler {
                enabled: !field.expanded
                onTapped: field.toggled()
            }
        }
    }

    MouseArea {
        anchors.fill: well
        enabled: field.cell && (field.cell.box || field.cell.editor === "menu")
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (field.cell.box)
                field.open(field.cell.index)
            else
                field.menu(field.cell)
        }
    }

    RaiseButton {
        id: sideBtn
        anchors.right: parent.right
        anchors.bottom: well.bottom
        width: 32
        height: 32
        visible: field.cell && (field.cell.box || field.cell.editor === "kuid" || field.cell.editor === "file" || field.cell.editor === "menu")
        fontName: bridge.iconFont
        glyph: !field.cell ? "" : (field.cell.editor === "kuid" ? "\ue1a1" : (field.cell.editor === "file" ? "\ue2c8" : "\ue5cc"))
        tip: !field.cell ? "" : (field.cell.box ? qsTr("Open") : (field.cell.editor === "file" ? qsTr("Choose file") : (field.cell.editor === "menu" ? qsTr("Choose") : qsTr("Pick from the library"))))
        onClicked: {
            if (!field.cell)
                return
            if (field.cell.box)
                field.open(field.cell.index)
            else if (field.cell.editor === "file")
                field.browse(field.cell.index)
            else if (field.cell.editor === "menu")
                field.menu(field.cell)
            else
                field.pick(field.cell.index)
        }
    }

    Row {
        id: chips
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: well.bottom
        anchors.topMargin: 2
        height: visible ? 18 : 0
        spacing: 8
        visible: field.cell && field.cell.editor === "enum" && field.cell.options && field.cell.options.length > 0
        Repeater {
            model: field.cell && field.cell.options ? field.cell.options : []
            delegate: Text {
                required property string modelData
                text: modelData
                color: field.cell && modelData === field.cell.value ? "#ff7a3c" : (bridge.dark ? "#8b93a1" : "#5c6570")
                font.pixelSize: 11
                MouseArea {
                    anchors.fill: parent
                    onClicked: field.commit(field.cell.index, modelData)
                }
            }
        }
    }
}
