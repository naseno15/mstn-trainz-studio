import QtQuick

// Optional update chip. The body opens the install dialog; the mark dismisses it.
Item {
    id: root
    readonly property bool dark: upd.dark

    Rectangle {
        anchors.fill: parent
        anchors.margins: 4
        radius: 14
        color: "transparent"
        border.width: 6
        border.color: Qt.rgba(1, 0.35, 0.12, root.dark ? 0.10 : 0.08)
    }

    Rectangle {
        id: plate
        anchors.fill: parent
        anchors.margins: 6
        radius: 12
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, root.dark ? 0.19 : 0.63)
        gradient: Gradient {
            GradientStop { position: 0.0; color: root.dark ? Qt.rgba(48 / 255, 54 / 255, 64 / 255, 0.94) : Qt.rgba(246 / 255, 248 / 255, 251 / 255, 0.96) }
            GradientStop { position: 1.0; color: root.dark ? Qt.rgba(16 / 255, 20 / 255, 26 / 255, 0.96) : Qt.rgba(220 / 255, 226 / 255, 234 / 255, 0.96) }
        }

        Row {
            z: 1
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 8
            spacing: 8

            Rectangle {
                width: 22
                height: 22
                radius: 7
                anchors.verticalCenter: parent.verticalCenter
                color: Qt.rgba(1, 0.35, 0.12, 0.22)
                Text {
                    anchors.centerIn: parent
                    text: "↑"
                    color: "#ff5a1f"
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            Column {
                width: parent.width - 22 - 28 - 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                Text {
                    width: parent.width
                    text: qsTr("Update available")
                    elide: Text.ElideRight
                    color: root.dark ? "#f5f5f7" : "#1d1d1f"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    text: qsTr("Version %1 is ready").arg(upd.version)
                    elide: Text.ElideRight
                    color: root.dark ? Qt.rgba(235 / 255, 235 / 255, 245 / 255, 0.62) : Qt.rgba(29 / 255, 29 / 255, 31 / 255, 0.58)
                    font.pixelSize: 12
                }
            }

            Rectangle {
                width: 22
                height: 22
                radius: 7
                anchors.verticalCenter: parent.verticalCenter
                color: closeHover.containsMouse ? Qt.rgba(1, 0.27, 0.23, 0.28) : "transparent"
                Text {
                    anchors.centerIn: parent
                    text: "×"
                    color: root.dark ? "#c8cdd6" : "#3a4150"
                    font.pixelSize: 14
                    font.bold: true
                }
                MouseArea {
                    id: closeHover
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: upd.dismiss()
                }
            }
        }

        MouseArea {
            z: 0
            anchors.fill: parent
            anchors.rightMargin: 36
            cursorShape: Qt.PointingHandCursor
            onClicked: upd.openDialog()
        }
    }
}
