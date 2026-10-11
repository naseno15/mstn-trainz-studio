import QtQuick

// Error / previous-session crash sheet. Same raised glass as the studios.
Item {
    id: root
    readonly property bool about: bridge.kind === "about"

    // Soft grey-black veil over the whole app so the card does not fight the page behind it.
    Rectangle {
        id: scrim
        anchors.fill: parent
        color: Qt.rgba(0.04, 0.05, 0.07, bridge.dark ? 0.62 : 0.42)
        opacity: 0
        MouseArea { anchors.fill: parent }
        Component.onCompleted: opacity = 1
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }

    GlassPlate {
        id: card
        anchors.centerIn: parent
        anchors.verticalCenterOffset: rise
        width: Math.min(root.about ? 520 : 580, parent.width - 48)
        height: Math.min(root.about ? 640 : 500, parent.height - 48)
        dark: bridge.dark
        matte: true
        plateRadius: 18
        opacity: 0
        scale: 0.96
        property real rise: 18
        Component.onCompleted: { rise = 0; scale = 1; opacity = 1 }
        Behavior on rise { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

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
                    color: root.about || bridge.kind === "log" ? Qt.rgba(1, 0.35, 0.12, 0.18) : bridge.kind === "warning" ? Qt.rgba(1, 0.62, 0.04, 0.22) : Qt.rgba(1, 0.27, 0.23, 0.22)
                    Text {
                        anchors.centerIn: parent
                        text: root.about ? "i" : bridge.kind === "log" ? qsTr("≡") : bridge.kind === "warning" ? "!" : qsTr("×")
                        color: root.about || bridge.kind === "log" ? "#ff5a1f" : bridge.kind === "warning" ? "#ff9f0a" : "#ff453a"
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
                visible: !root.about
                text: bridge.kind === "log" ? qsTr("Messages — newest at the bottom") : qsTr("Traceback — select text or use Copy")
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
                font.bold: true
            }

            Column {
                visible: root.about
                width: parent.width
                spacing: 8

                LogoMark { cap: 180 }
                Text {
                    text: qsTr("Made by")
                    color: bridge.dark ? "#8b93a1" : "#5c6570"
                    font.pixelSize: 11
                    font.bold: true
                }
                Text {
                    text: "MSTN Production"
                    color: "#ff5a1f"
                    font.pixelSize: 22
                    font.bold: true
                }
                Text {
                    width: parent.width
                    text: qsTr("Since 2024")
                    color: bridge.dark ? "#d5d8e0" : "#1d1d1f"
                    font.pixelSize: 13
                }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("A workbench for Trainz content — meshes, sounds, enginespecs, and asset packages — so the repetitive parts of development stay out of the way.")
                    color: bridge.dark ? "#c5cad3" : "#3a4150"
                    font.pixelSize: 13
                    lineHeight: 1.35
                }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: qsTr("Mesh Studio, Sounds Studio, Engine Tuner, and Assets Tools share this window.")
                    color: bridge.dark ? "#a8b0bc" : "#5c6570"
                    font.pixelSize: 12
                    lineHeight: 1.3
                }

                Text {
                    text: qsTr("Contact")
                    color: bridge.dark ? "#8b93a1" : "#5c6570"
                    font.pixelSize: 11
                    font.bold: true
                    topPadding: 4
                }
                Repeater {
                    model: [
                        { mark: "f", name: qsTr("Facebook"), value: "facebook.com/mstnproduction", url: "https://www.facebook.com/mstnproduction" },
                        { mark: "w", name: qsTr("Website"), value: "mstn.in.th", url: "https://www.mstn.in.th/" },
                        { mark: "@", name: qsTr("Email"), value: "mstnprod@gmail.com", url: "mailto:mstnprod@gmail.com" }
                    ]
                    delegate: Rectangle {
                        required property var modelData
                        width: parent.width
                        height: 36
                        radius: 10
                        color: linkHover.containsMouse
                               ? (bridge.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.06))
                               : (bridge.dark ? Qt.rgba(1, 1, 1, 0.04) : Qt.rgba(0, 0, 0, 0.03))
                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 10
                            Rectangle {
                                width: 22
                                height: 22
                                radius: 6
                                anchors.verticalCenter: parent.verticalCenter
                                color: Qt.rgba(1, 0.35, 0.12, 0.18)
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.mark
                                    color: "#ff5a1f"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                            }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 0
                                Text {
                                    text: modelData.name
                                    color: bridge.dark ? "#f2f3f5" : "#1d1d1f"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                                Text {
                                    text: modelData.value
                                    color: bridge.dark ? "#a8b0bc" : "#5c6570"
                                    font.pixelSize: 11
                                }
                            }
                        }
                        MouseArea {
                            id: linkHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: bridge.openUrl(modelData.url)
                        }
                    }
                }
            }

            Rectangle {
                visible: !root.about
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
                        wrapMode: root.about ? TextEdit.Wrap : TextEdit.NoWrap
                        color: bridge.dark ? "#e6e8ee" : "#1d1d1f"
                        font.family: "Cascadia Mono, Consolas"
                        font.pixelSize: 12
                        selectionColor: "#ff5a1f"
                    }
                }
            }

            Text {
                visible: !root.about
                width: parent.width
                text: (typeof bridge.logPath === "string" ? qsTr(bridge.logPath) : bridge.logPath)
                color: bridge.dark ? "#8b93a1" : "#5c6570"
                font.pixelSize: 11
                elide: Text.ElideMiddle
            }

            Row {
                width: parent.width
                spacing: root.about ? 0 : 8

                RaiseButton {
                    visible: !root.about
                    label: qsTr("Open log folder")
                    width: root.about ? 0 : 148
                    onClicked: bridge.openFolder()
                }
                RaiseButton {
                    visible: !root.about
                    label: (typeof bridge.copyLabel === "string" ? qsTr(bridge.copyLabel) : bridge.copyLabel)
                    width: root.about ? 0 : 120
                    tip: qsTr("Copy title, summary, traceback, and log path")
                    onClicked: bridge.copyError(trace.selectedText)
                }
                Item { width: Math.max(0, parent.width - (root.about ? 0 : 148 + 120 + 16) - 110); height: 1 }
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
