import QtQuick

// Sunk glass field. Buttons stay RaiseButton.
Item {
    id: field

    property string label: ""
    property string value: ""
    property bool fieldEnabled: true
    signal edited(string text)

    implicitHeight: 32
    width: parent ? parent.width : 180
    opacity: fieldEnabled ? 1 : 0.4

    Text {
        id: lab
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: field.label.length > 0 ? 72 : 0
        text: field.label
        color: bridge.dark ? "#8b93a1" : "#5c6570"
        font.pixelSize: 11
        elide: Text.ElideRight
        visible: field.label.length > 0
    }

    Item {
        anchors.left: lab.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: field.label.length > 0 ? 6 : 0

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
        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            verticalAlignment: TextInput.AlignVCenter
            color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
            font.pixelSize: 12
            selectByMouse: true
            enabled: field.fieldEnabled
            text: field.value
            onEditingFinished: field.edited(text)
        }
    }
}
