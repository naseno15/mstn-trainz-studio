import QtQuick

// Engine Tuner sidebar — same blocks as the frost panel: logo, enginespec, clone, file icons.
GlassPlate {
    id: side

    dark: bridge.dark
    plateRadius: 16
    foot: 8
    property real footPad: 0

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    Item {
        anchors.fill: parent

        Column {
            id: head
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 8

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 108
                height: 36
                fillMode: Image.PreserveAspectFit
                source: bridge.dark ? "image://mstnlogo/dark" : "image://mstnlogo/light"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Engine Tuner"
                color: side.ink
                font.pixelSize: 15
                font.bold: true
            }
            RaiseButton {
                width: 40
                height: 40
                accent: true
                glyph: bridge.showBack ? bridge.backGlyph : bridge.openGlyph
                fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                onClicked: bridge.showBack ? bridge.goBack() : bridge.openFile()
            }
        }

        Column {
            id: foot
            anchors.bottom: parent.bottom
            anchors.bottomMargin: side.footPad
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 6

            Rectangle {
                width: parent.width
                height: 1
                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
            }
            Text {
                text: "File"
                color: side.mute
                font.pixelSize: 11
            }
            Row {
                spacing: 6
                RaiseButton {
                    width: 36
                    height: 36
                    accent: true
                    glyph: bridge.saveGlyph
                    fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                    onClicked: bridge.saveFile()
                }
                RaiseButton {
                    width: 36
                    height: 36
                    glyph: bridge.saveAsGlyph
                    fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                    enabled: bridge.saveAsOn
                    onClicked: bridge.saveFileAs()
                }
                RaiseButton {
                    width: 36
                    height: 36
                    glyph: bridge.undoGlyph
                    fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                    onClicked: bridge.undoEdit()
                }
                RaiseButton {
                    width: 36
                    height: 36
                    glyph: bridge.redoGlyph
                    fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                    onClicked: bridge.redoEdit()
                }
            }
        }

        Flickable {
            anchors.top: head.bottom
            anchors.bottom: foot.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.topMargin: 10
            anchors.bottomMargin: 10
            contentHeight: mid.height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Column {
                id: mid
                width: parent.width
                spacing: 10

                Rectangle {
                    width: parent.width
                    height: infoCol.height + 16
                    radius: 12
                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
                    Column {
                        id: infoCol
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.margins: 8
                        spacing: 4
                        Text {
                            text: "Enginespec"
                            color: side.ink
                            font.pixelSize: 13
                            font.bold: true
                        }
                        Repeater {
                            model: JSON.parse(bridge.sideJson || "[]")
                            delegate: Item {
                                required property var modelData
                                width: infoCol.width
                                height: 18
                                Text {
                                    id: cap
                                    text: modelData.cap
                                    color: side.mute
                                    font.pixelSize: 12
                                }
                                Text {
                                    anchors.left: cap.right
                                    anchors.right: parent.right
                                    anchors.leftMargin: 8
                                    text: modelData.val
                                    color: side.ink
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideLeft
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    width: parent.width
                    height: cloneCol.height + 16
                    radius: 12
                    color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
                    Column {
                        id: cloneCol
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.margins: 8
                        spacing: 8
                        Text {
                            text: "Clone curves"
                            color: side.ink
                            font.pixelSize: 13
                            font.bold: true
                        }
                        Row {
                            spacing: 8
                            Text {
                                text: "From"
                                color: side.mute
                                font.pixelSize: 12
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Rectangle {
                                width: 28
                                height: 26
                                radius: 8
                                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.06 : 0.5)
                                Text { anchors.centerIn: parent; text: "−"; color: side.ink; font.pixelSize: 16 }
                                TapHandler { onTapped: bridge.setCloneFrom(bridge.cloneFrom - 1) }
                            }
                            Text {
                                text: bridge.cloneFrom
                                color: side.ink
                                font.pixelSize: 14
                                font.bold: true
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Rectangle {
                                width: 28
                                height: 26
                                radius: 8
                                color: Qt.rgba(1, 1, 1, bridge.dark ? 0.06 : 0.5)
                                Text { anchors.centerIn: parent; text: "+"; color: side.ink; font.pixelSize: 16 }
                                TapHandler { onTapped: bridge.setCloneFrom(bridge.cloneFrom + 1) }
                            }
                        }
                        Text {
                            text: "Targets"
                            color: side.mute
                            font.pixelSize: 12
                        }
                        Grid {
                            columns: 4
                            columnSpacing: 8
                            rowSpacing: 6
                            Repeater {
                                model: 8
                                delegate: Column {
                                    required property int index
                                    property int notch: index + 1
                                    width: 36
                                    spacing: 2
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: notch
                                        color: side.ink
                                        font.pixelSize: 11
                                        font.bold: true
                                    }
                                    Rectangle {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: 16
                                        height: 16
                                        radius: 4
                                        border.width: 1
                                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.25 : 0.45)
                                        color: (bridge.targets & (1 << notch)) ? "#ff5a1f" : "transparent"
                                        TapHandler { onTapped: bridge.toggleTarget(notch) }
                                    }
                                }
                            }
                        }
                        Row {
                            width: parent.width
                            spacing: 6
                            RaiseButton {
                                width: (parent.width - 6) / 2
                                label: "Clone"
                                onClicked: bridge.doClone()
                            }
                            RaiseButton {
                                width: (parent.width - 6) / 2
                                label: "→ N+1..8"
                                onClicked: bridge.doCloneHigher()
                            }
                        }
                    }
                }

                Text {
                    width: parent.width
                    text: "Use the bottom bar to switch Tuner · Simulation · Parameters."
                    color: side.mute
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
