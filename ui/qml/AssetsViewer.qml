import QtQuick

// Packages right dock chrome. Preview (image / text / mesh) stays a widget in the well.
Item {
    id: viewer

    function tip(key) {
        try {
            var bag = JSON.parse(bridge.viewTips)
            return bag[key] || ""
        } catch (e) {
            return ""
        }
    }

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    property real padTop: 22 + head.height + hint.height
    property real padBottom: foot.height + 28

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    GlassPlate {
        anchors.fill: parent
        visible: viewer.width > 40
        dark: bridge.dark
        plateRadius: 16
        foot: 8

        Item {
            id: body
            anchors.fill: parent

            Column {
                id: head
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 8

                Text {
                    width: parent.width
                    text: bridge.viewTitle
                    color: viewer.ink
                    font.pixelSize: 15
                    font.bold: true
                    elide: Text.ElideRight
                }

                Row {
                    width: parent.width
                    spacing: 6

                    Item {
                        id: tabs
                        width: Math.min(168, parent.width * 0.46)
                        height: 36

                        Rectangle {
                            anchors.fill: parent
                            radius: 12
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                            border.width: 1
                            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
                        }
                        Item {
                            id: tabPill
                            z: 1
                            y: 3
                            height: 30
                            width: (tabs.width - 6) / 2
                            x: 3 + bridge.viewPane * width
                            Behavior on x { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

                            Repeater {
                                model: 3
                                delegate: Rectangle {
                                    required property int index
                                    property real t: (index + 1) / 3
                                    anchors.fill: parent
                                    anchors.leftMargin: 1 - t * 2
                                    anchors.rightMargin: 1 - t * 2
                                    anchors.topMargin: 1 + index
                                    anchors.bottomMargin: -t * 2
                                    radius: 10
                                    color: Qt.rgba(0, 0, 0, 0.22 * (1.05 - t))
                                }
                            }
                            Rectangle {
                                anchors.fill: parent
                                anchors.bottomMargin: 2
                                radius: 10
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: "#ff7a45" }
                                    GradientStop { position: 0.42; color: "#ff5a1f" }
                                    GradientStop { position: 1.0; color: "#c43a10" }
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    anchors.topMargin: 1
                                    height: 1
                                    color: Qt.rgba(1, 1, 1, 0.55)
                                }
                            }
                        }
                        Row {
                            z: 2
                            anchors.fill: parent
                            Repeater {
                                model: [
                                    { key: 0, label: "Viewer", on: true },
                                    { key: 1, label: "Editor", on: bridge.viewEditor }
                                ]
                                delegate: Item {
                                    required property var modelData
                                    width: tabs.width / 2
                                    height: tabs.height
                                    opacity: modelData.on ? 1 : 0.35
                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData.label
                                        color: bridge.viewPane === modelData.key ? "#ffffff" : viewer.ink
                                        font.pixelSize: 12
                                        font.bold: bridge.viewPane === modelData.key
                                    }
                                    TapHandler {
                                        onTapped: if (modelData.on) bridge.setViewerPane(modelData.key)
                                    }
                                }
                            }
                        }
                    }

                    RaiseButton {
                        width: 36
                        height: 36
                        label: "A−"
                        tip: viewer.tip("smaller")
                        onClicked: bridge.viewerFont(-1)
                    }
                    Text {
                        width: 44
                        height: 36
                        text: bridge.viewFont
                        color: viewer.mute
                        font.pixelSize: 11
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    RaiseButton {
                        width: 36
                        height: 36
                        label: "A+"
                        tip: viewer.tip("larger")
                        onClicked: bridge.viewerFont(1)
                    }
                    Item { width: 1; height: 1 }
                    RaiseButton {
                        width: 36
                        height: 36
                        enabled: bridge.viewNested
                        opacity: enabled ? 1 : 0.35
                        glyph: bridge.glyphBack
                        tip: viewer.tip("back")
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        onClicked: bridge.viewerBack()
                    }
                    RaiseButton {
                        width: 36
                        height: 36
                        glyph: bridge.glyphExpand
                        tip: viewer.tip("expand")
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        onClicked: bridge.viewerExpand()
                    }
                }
            }

            Text {
                id: hint
                anchors.top: head.bottom
                anchors.topMargin: 8
                anchors.left: parent.left
                anchors.right: parent.right
                text: bridge.viewHint
                color: viewer.mute
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }

            Column {
                id: foot
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 6

                Flow {
                    width: parent.width
                    spacing: 6

                    RaiseButton {
                        visible: bridge.viewSaveOn
                        width: 36
                        height: 36
                        accent: true
                        glyph: bridge.glyphSave
                        tip: viewer.tip("saveText")
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        onClicked: bridge.viewerSave()
                    }
                    RaiseButton {
                        visible: bridge.viewEngine
                        height: 36
                        label: bridge.viewEngineLabel
                        onClicked: bridge.viewerEngine()
                    }
                    RaiseButton {
                        visible: bridge.viewFast
                        height: 36
                        label: bridge.viewFastLabel
                        onClicked: bridge.viewerFast()
                    }
                    RaiseButton {
                        visible: bridge.viewMesh
                        height: 36
                        label: bridge.viewMeshLabel
                        onClicked: bridge.viewerMesh()
                    }
                    RaiseButton {
                        height: 36
                        label: bridge.viewRepl
                        onClicked: bridge.viewerReplace()
                    }
                    RaiseButton {
                        width: 36
                        height: 36
                        glyph: bridge.glyphDelete
                        tip: viewer.tip("delete")
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        onClicked: bridge.viewerDelete()
                    }
                    RaiseButton {
                        width: 36
                        height: 36
                        accent: true
                        glyph: bridge.glyphSave
                        tip: viewer.tip("saveCdp")
                        fontName: mi.name.length > 0 ? mi.name : bridge.iconFont
                        onClicked: bridge.viewerSaveCdp()
                    }
                }
                RaiseButton {
                    width: parent.width
                    height: 36
                    label: bridge.viewFbx
                    onClicked: bridge.viewerDeleteFbx()
                }
            }
        }
    }
}
