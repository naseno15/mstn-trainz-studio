import QtQuick

// Error / previous-session crash sheet. Same raised glass as the studios.
Item {
    id: root

    // Soft grey-black veil over the whole app so the card does not fight the page behind it.
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0.04, 0.05, 0.07, bridge.dark ? 0.45 : 0.28)
        MouseArea { anchors.fill: parent }  // swallow clicks outside the card
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
                    color: bridge.kind === "log" ? Qt.rgba(1, 0.35, 0.12, 0.18) : bridge.kind === "warning" ? Qt.rgba(1, 0.62, 0.04, 0.22) : Qt.rgba(1, 0.27, 0.23, 0.22)
                    Text {
                        anchors.centerIn: parent
                        text: bridge.kind === "log" ? qsTr("≡") : bridge.kind === "warning" ? "!" : qsTr("×")
                        color: bridge.kind === "log" ? "#ff5a1f" : bridge.kind === "warning" ? "#ff9f0a" : "#ff453a"
                        font.pixelSize: 20
                        font.bold: true
                    }
                }

                Column {
                    width: parent.width - 52
                    spacing: 2
                    Text {
                        width: parent.width
                        text: (typeof bridge.title === "string" ? qsTr(bridge.title) : bridge.title)
                        color: bridge.dark ? "#f2f3f5" : "#1d1d1f"
                        font.pixelSize: 16
                        font.bold: true
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        width: parent.width
                        text: (typeof bridge.summary === "string" ? qsTr(bridge.summary) : bridge.summary)
                        color: bridge.dark ? "#a8b0bc" : "#5c6570"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                }
            }

            Text {
                text: bridge.kind === "log" ? qsTr("Messages — newest at the bottom") : qsTr("Traceback — select text or use Copy")
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
                    Component.onCompleted: if (bridge.kind === "log") contentY = Math.max(0, contentHeight - height)

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
                text: (typeof bridge.logPath === "string" ? qsTr(bridge.logPath) : bridge.logPath)
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
                elide: Text.ElideMiddle
            }

            Row {
                width: parent.width
                spacing: 8

                RaiseButton {
                    label: qsTr("Open log folder")
                    width: 148
                    onClicked: bridge.openFolder()
                }
                RaiseButton {
                    label: (typeof bridge.copyLabel === "string" ? qsTr(bridge.copyLabel) : bridge.copyLabel)
                    width: 120
                    tip: qsTr("Copy title, summary, traceback, and log path")
                    onClicked: bridge.copyError(trace.selectedText)
                }
                Item { width: Math.max(0, parent.width - 148 - 120 - 110 - 24); height: 1 }
                RaiseButton {
                    label: qsTr("OK")
                    accent: true
                    width: 110
                    tip: bridge.quitOnOk ? qsTr("Close Trainz Studio") : ""
                    onClicked: bridge.dismiss()
                }
            }
        }
    }
}
