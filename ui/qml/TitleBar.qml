import QtQuick

Item {
    id: root

    Repeater {
        model: 5
        delegate: Rectangle {
            required property int index
            property real t: (index + 1) / 5
            property real spread: 8 + t * 16
            anchors.fill: parent
            anchors.leftMargin: 10 - spread * 0.45
            anchors.rightMargin: 10 - spread * 0.45
            anchors.topMargin: 8 + index * 0.6
            anchors.bottomMargin: 2 - t * 4
            radius: 24
            color: Qt.rgba(0, 0, 0, (bridge.dark ? 0.20 : 0.09) * (1.05 - t))
        }
    }

    Rectangle {
        id: capsule
        anchors.fill: parent
        anchors.margins: 8
        anchors.bottomMargin: 14
        radius: 22
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.22 : 0.75)
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.82) }
            GradientStop { position: 0.5; color: bridge.dark ? Qt.rgba(0.14, 0.16, 0.20, 0.78) : Qt.rgba(0.91, 0.93, 0.96, 0.88) }
            GradientStop { position: 1.0; color: bridge.dark ? Qt.rgba(0.06, 0.07, 0.09, 0.88) : Qt.rgba(0.80, 0.84, 0.90, 0.92) }
        }

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 28
            anchors.rightMargin: 28
            anchors.topMargin: 1
            height: 1
            color: Qt.rgba(1, 1, 1, bridge.dark ? 0.18 : 0.45)
        }

        Row {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 14
            spacing: 8

            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Rectangle {
                    width: 13; height: 13; radius: 6.5; color: "#ff5f57"
                    TapHandler { onTapped: bridge.requestClose() }
                }
                Rectangle {
                    width: 13; height: 13; radius: 6.5; color: "#febc2e"
                    TapHandler { onTapped: bridge.requestMin() }
                }
                Rectangle {
                    width: 13; height: 13; radius: 6.5; color: "#28c840"
                    TapHandler { onTapped: bridge.requestZoom() }
                }
            }

            Repeater {
                model: bridge.menus
                delegate: Rectangle {
                    id: menuBtn
                    required property string key
                    required property string label
                    width: labelText.implicitWidth + 22
                    height: 34
                    radius: 12
                    anchors.verticalCenter: parent.verticalCenter
                    color: bridge.openKey === menuBtn.key
                           ? "#ff5a1f"
                           : (menuHover.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent")
                    Text {
                        id: labelText
                        anchors.centerIn: parent
                        text: menuBtn.label
                        color: bridge.openKey === menuBtn.key
                               ? "#ffffff"
                               : (bridge.dark ? "#f2f4f8" : "#1d1d1f")
                        font.pixelSize: 13
                    }
                    HoverHandler { id: menuHover }
                    TapHandler {
                        onTapped: bridge.toggleMenu(menuBtn.key, menuBtn.mapToGlobal(0, menuBtn.height).x, menuBtn.mapToGlobal(0, menuBtn.height).y)
                    }
                }
            }

            Item { width: 8; height: 1 }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(40, parent.width - x - 8)
                text: bridge.windowTitle
                color: bridge.dark ? "#9aa3b2" : "#5c6570"
                font.pixelSize: 12
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.SizeAllCursor
                    onPressed: bridge.startMove()
                }
            }
        }
    }
}
