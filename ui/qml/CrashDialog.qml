import QtQuick

// Error / previous-session crash sheet. Same raised glass as the studios.
Item {
    id: root

    Rectangle {
        anchors.fill: parent
        color: bridge.dark ? "#e0101418" : "#e8eef1f6"
    }

    GlassPlate {
        id: card
        anchors.centerIn: parent
        width: Math.min(580, parent.width - 48)
        height: Math.min(500, parent.height - 48)
        dark: bridge.dark
        plateRadius: 18

        Column {
            anchors.fill: parent
            spacing: 10

            Row {
                width: parent.width
                spacing: 12

                Rectangle {
                    width: 40
                    height: 40
                    radius: 12
                    color: bridge.kind === "warning" ? Qt.rgba(1, 0.62, 0.04, 0.22) : Qt.rgba(1, 0.27, 0.23, 0.22)
                    Text {
                        anchors.centerIn: parent
                        text: bridge.kind === "warning" ? "!" : "×"
                        color: bridge.kind === "warning" ? "#ff9f0a" : "#ff453a"
                        font.pixelSize: 20
                        font.bold: true
                    }
                }

                Column {
                    width: parent.width - 52
                    spacing: 2
                    Text {
                        width: parent.width
                        text: bridge.title
                        color: bridge.dark ? "#f2f3f5" : "#1d1d1f"
                        font.pixelSize: 16
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: bridge.summary
                        color: bridge.dark ? "#a8b0bc" : "#5c6570"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Text {
                text: "Traceback — select text or use Copy"
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
                font.bold: true
            }

            Rectangle {
                width: parent.width
                height: Math.max(140, card.height - 250)
                radius: 12
                color: bridge.dark ? Qt.rgba(0.03, 0.04, 0.06, 0.55) : Qt.rgba(1, 1, 1, 0.72)
                border.width: 1
                border.color: bridge.dark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(0, 0, 0, 0.10)
                clip: true

                Flickable {
                    id: scroller
                    anchors.fill: parent
                    anchors.margins: 8
                    contentWidth: trace.contentWidth
                    contentHeight: trace.contentHeight
                    clip: true
                    flickableDirection: Flickable.HorizontalAndVerticalFlick

                    TextEdit {
                        id: trace
                        width: Math.max(scroller.width, contentWidth)
                        text: bridge.detail
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.NoWrap
                        color: bridge.dark ? "#e6e8ee" : "#1d1d1f"
                        font.family: "Cascadia Mono, Consolas"
                        font.pixelSize: 12
                        selectionColor: "#ff5a1f"
                    }
                }
            }

            Text {
                width: parent.width
                text: bridge.logPath
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
                elide: Text.ElideMiddle
            }

            Row {
                width: parent.width
                spacing: 8

                RaiseButton {
                    label: "Open log folder"
                    width: 148
                    onClicked: bridge.openFolder()
                }
                RaiseButton {
                    label: bridge.copyLabel
                    width: 120
                    tip: "Copy title, summary, traceback, and log path"
                    onClicked: bridge.copyError(trace.selectedText)
                }
                Item { width: Math.max(0, parent.width - 148 - 120 - 110 - 24); height: 1 }
                RaiseButton {
                    label: "OK"
                    accent: true
                    width: 110
                    tip: bridge.quitOnOk ? "Close Trainz Studio" : ""
                    onClicked: bridge.dismiss()
                }
            }
        }
    }
}
