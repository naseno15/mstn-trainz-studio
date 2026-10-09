import QtQuick

// Sunk glass field. Buttons stay RaiseButton.
// unit sits inside the well, right side, behind a divider. It is not editable.
Item {
    id: field

    property string label: ""
    property string unit: ""
    property bool unitTap: false
    property string value: ""
    property bool fieldEnabled: true
    property bool hasCheck: false
    property bool checked: false
    property bool stacked: false
    signal edited(string text)
    signal toggled()
    signal unitClicked()

    implicitHeight: stacked && label.length > 0 ? 48 : 32
    width: parent ? parent.width : 180
    opacity: fieldEnabled ? 1 : 0.4

    Text {
        id: topLab
        visible: field.stacked && field.label.length > 0
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: visible ? 14 : 0
        text: (typeof field.label === "string" ? qsTr(field.label) : field.label)
        color: bridge.dark ? "#8b93a1" : "#5c6570"
        font.pixelSize: 11
        elide: Text.ElideRight
    }

    Item {
        id: labBox
        visible: !field.stacked
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: !field.stacked && (field.label.length > 0 || field.hasCheck) ? 72 : 0
        height: 18

        Rectangle {
            visible: field.hasCheck
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: 18
            height: 18
            radius: 5
            color: field.checked ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.08)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.2)
            Text {
                anchors.centerIn: parent
                visible: field.checked
                text: qsTr("✓")
                color: "#ffffff"
                font.pixelSize: 12
            }
            TapHandler { onTapped: field.toggled() }
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: field.hasCheck ? 22 : 0
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: (typeof field.label === "string" ? qsTr(field.label) : field.label)
            color: bridge.dark ? "#8b93a1" : "#5c6570"
            font.pixelSize: 11
            elide: Text.ElideRight
            visible: field.label.length > 0
        }
    }

    Item {
        id: well
        anchors.left: labBox.right
        anchors.right: parent.right
        anchors.top: topLab.bottom
        anchors.bottom: parent.bottom
        anchors.leftMargin: labBox.width > 0 ? 6 : 0
        anchors.topMargin: topLab.visible ? 2 : 0

        Rectangle {
            anchors.fill: parent
            radius: 8
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
        }
        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 1
            height: 7
            radius: 7
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.12) }
                GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0) }
            }
        }

        Item {
            id: unitBox
            visible: field.unit.length > 0
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: visible ? unitText.implicitWidth + 16 : 0

            Rectangle {
                width: 1
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.topMargin: 6
                anchors.bottomMargin: 6
                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.35)
            }
            Text {
                id: unitText
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: (typeof field.unit === "string" ? qsTr(field.unit) : field.unit)
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
            }
            HoverHandler {
                enabled: field.unitTap
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                enabled: field.unitTap
                onTapped: field.unitClicked()
            }
        }

        TextInput {
            id: input
            anchors.left: parent.left
            anchors.right: unitBox.visible ? unitBox.left : parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.leftMargin: 8
            anchors.rightMargin: 6
            verticalAlignment: TextInput.AlignVCenter
            color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
            font.pixelSize: 12
            selectByMouse: true
            enabled: field.fieldEnabled
            clip: true
            text: field.value
            onEditingFinished: field.edited(text)
        }
    }
}
