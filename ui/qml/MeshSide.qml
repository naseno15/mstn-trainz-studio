import QtQuick

// Left Mesh Studio sidebar. Lists and controls call the hidden widgets.
Item {
    id: side

    readonly property var bag: {
        try { return JSON.parse(bridge.sideJson) } catch (e) { return {} }
    }
    readonly property color ink: bridge.dark ? "#f4f6fa" : "#1c1c1e"
    readonly property color mute: bridge.dark ? "#9aa3b2" : "#5c6570"

    function slide(key, min, max, value) {
        var span = Math.max(1, max - min)
        return (value - min) / span
    }

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
            source: "image://mstnlogo/" + (bridge.dark ? "dark" : "light")
        }
        Item {
            id: tabWell
            width: parent.width
            height: 40
            property int pressIndex: -1
            readonly property int count: Math.max(1, (side.bag.tabs || []).length)
            readonly property real sink: pressIndex >= 0 ? 1 : 0

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
                y: 3 + tabWell.sink * 2
                height: 34 - tabWell.sink * 2
                width: (tabWell.width - 6) / tabWell.count
                x: 3 + side.bag.tab * width
                Behavior on x { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                Behavior on height { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }

                Repeater {
                    model: 3
                    delegate: Rectangle {
                        required property int index
                        property real t: (index + 1) / 3
                        anchors.fill: parent
                        anchors.leftMargin: 1 - t * 2
                        anchors.rightMargin: 1 - t * 2
                        anchors.topMargin: 1 + index
                        anchors.bottomMargin: -t * 2 * (1 - tabWell.sink)
                        radius: 10
                        opacity: 1 - tabWell.sink
                        color: Qt.rgba(0, 0, 0, 0.22 * (1.05 - t))
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: tabWell.sink * 2
                    anchors.bottomMargin: 2 * (1 - tabWell.sink)
                    radius: 10
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#ff7a45" }
                        GradientStop { position: 0.42; color: "#ff5a1f" }
                        GradientStop { position: 1.0; color: "#c43a10" }
                    }
                }
            }
            Row {
                z: 2
                anchors.fill: parent
                Repeater {
                    model: side.bag.tabs || []
                    delegate: Item {
                        required property string modelData
                        required property int index
                        width: tabWell.width / tabWell.count
                        height: tabWell.height
                        Text {
                            anchors.centerIn: parent
                            text: modelData
                            color: index === side.bag.tab ? "#ffffff" : side.ink
                            font.pixelSize: 12
                            font.bold: index === side.bag.tab
                        }
                        TapHandler {
                            onPressedChanged: tabWell.pressIndex = pressed ? index : (tabWell.pressIndex === index ? -1 : tabWell.pressIndex)
                            onTapped: bridge.setSideTab(index)
                        }
                    }
                }
            }
        }
    }

    Flickable {
        id: scroller
        anchors.top: head.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: foot.top
        anchors.bottomMargin: 8
        contentWidth: width
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: body
            width: scroller.width
            spacing: 8

            Rectangle {
                width: parent.width
                height: infoCol.implicitHeight + 8
                radius: 10
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.18 : 0.05)
                Column {
                    id: infoCol
                    width: parent.width - 12
                    x: 6
                    y: 4
                    spacing: 4
                    Text {
                        text: (side.bag.infoOpen ? "▾  " : "▸  ") + "Mesh Info"
                        color: side.ink
                        font.pixelSize: 13
                        font.bold: true
                        TapHandler { onTapped: bridge.clickId("info") }
                    }
                    Column {
                        visible: side.bag.infoOpen === true
                        width: parent.width
                        spacing: 2
                        Repeater {
                            model: side.bag.stats || []
                            delegate: Row {
                                required property var modelData
                                width: parent.width
                                spacing: 8
                                Text { text: modelData.k; color: side.mute; font.pixelSize: 11; width: 88 }
                                Text { text: modelData.v; color: side.ink; font.pixelSize: 11; width: parent.width - 96; elide: Text.ElideRight }
                            }
                        }
                        Repeater {
                            model: side.bag.meshes || []
                            delegate: Row {
                                required property var modelData
                                required property int index
                                width: parent.width
                                height: 26
                                spacing: 6
                                Rectangle {
                                    width: 16
                                    height: 16
                                    radius: 4
                                    anchors.verticalCenter: parent.verticalCenter
                                    border.color: side.mute
                                    color: modelData.show ? "#ff5a1f" : "transparent"
                                    TapHandler { onTapped: bridge.toggleMesh(index, 0) }
                                }
                                Rectangle {
                                    width: 16
                                    height: 16
                                    radius: 4
                                    anchors.verticalCenter: parent.verticalCenter
                                    border.color: side.mute
                                    color: modelData.atts ? "#ff5a1f" : "transparent"
                                    TapHandler { onTapped: bridge.toggleMesh(index, 1) }
                                }
                                Text {
                                    text: modelData.name
                                    color: modelData.on ? "#ff5a1f" : side.ink
                                    font.pixelSize: 12
                                    width: parent.width - 50
                                    elide: Text.ElideRight
                                    anchors.verticalCenter: parent.verticalCenter
                                    TapHandler { onTapped: bridge.pickList("mesh", index) }
                                }
                            }
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 4
                visible: side.bag.tab === 0
                Text { text: side.bag.attTitle || "Attachments"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Text { visible: (side.bag.cap || "").length > 0; text: side.bag.cap || ""; color: side.mute; font.pixelSize: 11; width: parent.width; wrapMode: Text.Wrap }
                Repeater {
                    model: side.bag.atts || []
                    delegate: Rectangle {
                        required property string modelData
                        required property int index
                        width: body.width
                        height: 28
                        radius: 8
                        color: index === side.bag.att ? "#ff5a1f" : "transparent"
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            text: modelData
                            color: index === side.bag.att ? "#ffffff" : side.ink
                            font.pixelSize: 12
                        }
                        TapHandler { onTapped: bridge.pickList("atts", index) }
                    }
                }
                Row {
                    visible: side.bag.showDs === true
                    spacing: 8
                    Text {
                        text: side.bag.dsAll ? "☑ Select all" : "☐ Select all"
                        color: side.ink
                        font.pixelSize: 12
                        TapHandler { onTapped: bridge.setChecked("dsAll", !side.bag.dsAll) }
                    }
                }
                Repeater {
                    model: side.bag.sceneMeshes || []
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: body.width
                        height: 28
                        radius: 8
                        color: modelData.on ? Qt.rgba(1, 0.35, 0.12, 0.35) : "transparent"
                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            spacing: 8
                            Text {
                                text: modelData.ck ? "☑" : "☐"
                                color: side.ink
                                anchors.verticalCenter: parent.verticalCenter
                                TapHandler { onTapped: bridge.toggleSceneMesh(index) }
                            }
                            Text {
                                text: modelData.t
                                color: side.ink
                                font.pixelSize: 12
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                        TapHandler { onTapped: bridge.pickList("scene", index) }
                    }
                }
                Text {
                    visible: side.bag.dsOn === true
                    text: side.bag.dsLabel || ""
                    color: "#ff5a1f"
                    font.pixelSize: 12
                    font.bold: true
                    TapHandler { onTapped: bridge.clickId("dsApply") }
                }
                Text { text: "Viewport"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Text {
                    text: side.bag.face ? "☑ Face Orientation" : "☐ Face Orientation"
                    color: side.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("face", !side.bag.face) }
                }
            }

            Column {
                width: parent.width
                spacing: 4
                visible: side.bag.tab === 1
                Text { text: "Texture view"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Row {
                    spacing: 6
                    Repeater {
                        model: (side.bag.tex && side.bag.tex.items) || []
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: lab.implicitWidth + 16
                            height: 28
                            radius: 8
                            color: index === side.bag.tex.i ? "#ff5a1f" : Qt.rgba(1, 1, 1, bridge.dark ? 0.06 : 0.4)
                            Text { id: lab; anchors.centerIn: parent; text: modelData; color: index === side.bag.tex.i ? "#fff" : side.ink; font.pixelSize: 11 }
                            TapHandler { onTapped: bridge.setCombo("tex", index) }
                        }
                    }
                }
                Repeater {
                    model: side.bag.mats || []
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: body.width
                        height: 26
                        radius: 6
                        color: modelData.on ? "#ff5a1f" : "transparent"
                        Text {
                            x: 6 + modelData.d * 14
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - x - 4
                            text: modelData.t + (modelData.a ? "   " + modelData.a : "")
                            color: modelData.on ? "#fff" : side.ink
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        TapHandler { onTapped: bridge.pickMat(index) }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 4
                visible: side.bag.tab === 2
                Text { text: "Cabin glow"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Text {
                    text: side.bag.moon ? "☑ " + (side.bag.moonLab || "Moon") : "☐ Moon"
                    color: side.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("moon", !side.bag.moon) }
                }
                Slide { key: "moon"; lab: side.bag.moonLab || ""; min: 5; max: 120; val: side.bag.moonInt || 5 }
                Repeater {
                    model: side.bag.lamps || []
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: body.width
                        height: 26
                        radius: 6
                        color: modelData.on ? "#ff5a1f" : "transparent"
                        Text {
                            x: 6
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 10
                            text: modelData.t
                            color: modelData.on ? "#fff" : side.ink
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        TapHandler { onTapped: bridge.pickList("lamp", index) }
                    }
                }
                Text {
                    text: side.bag.lampOn ? "☑ Glow + cast" : "☐ Glow + cast"
                    color: side.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("lamp", !side.bag.lampOn) }
                }
                Slide { key: "bright"; lab: side.bag.brightLab || ""; min: 0; max: 800; val: side.bag.bright || 0 }
                Slide { key: "range"; lab: side.bag.rangeLab || ""; min: 5; max: 3000; val: side.bag.range || 5 }
                Text { text: "Color"; color: "#ff5a1f"; font.pixelSize: 12; TapHandler { onTapped: bridge.clickId("lampColor") } }
                Text {
                    text: side.bag.gizmo ? "☑ Lamp gizmos" : "☐ Lamp gizmos"
                    color: side.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("gizmo", !side.bag.gizmo) }
                }
                Text { text: "Add from Mat"; color: side.ink; font.pixelSize: 12; TapHandler { onTapped: bridge.clickId("lampAdd") } }
                Text { text: "Remove selected"; color: side.ink; font.pixelSize: 12; TapHandler { onTapped: bridge.clickId("lampRemove") } }
                Text { text: "Rescan"; color: side.ink; font.pixelSize: 12; TapHandler { onTapped: bridge.clickId("lampRescan") } }
                Text { text: "Bake"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Row {
                    spacing: 4
                    Repeater {
                        model: (side.bag.bake && side.bag.bake.items) || []
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: bl.implicitWidth + 12
                            height: 26
                            radius: 8
                            color: index === side.bag.bake.i ? "#ff5a1f" : "transparent"
                            Text { id: bl; anchors.centerIn: parent; text: modelData; color: index === side.bag.bake.i ? "#fff" : side.ink; font.pixelSize: 11 }
                            TapHandler { onTapped: bridge.setCombo("bake", index) }
                        }
                    }
                }
                Text {
                    text: side.bag.cuda ? "☑ CUDA" : "☐ CUDA"
                    color: side.bag.cudaOn ? side.ink : side.mute
                    font.pixelSize: 12
                    TapHandler { onTapped: if (side.bag.cudaOn) bridge.setChecked("cuda", !side.bag.cuda) }
                }
                Text { text: "Bake lamps"; color: "#ff5a1f"; font.pixelSize: 13; font.bold: true; TapHandler { onTapped: bridge.clickId("bake") } }
            }

            Column {
                width: parent.width
                spacing: 4
                visible: side.bag.tab === 3
                Text { text: "Animations"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Text { visible: side.bag.animEmpty === true; text: "No .kin beside this mesh"; color: side.mute; font.pixelSize: 12 }
                Repeater {
                    model: side.bag.anims || []
                    delegate: Rectangle {
                        required property string modelData
                        required property int index
                        width: body.width
                        height: 28
                        radius: 8
                        color: index === side.bag.anim ? "#ff5a1f" : "transparent"
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            x: 8
                            text: modelData
                            color: index === side.bag.anim ? "#fff" : side.ink
                            font.pixelSize: 12
                        }
                        TapHandler { onTapped: bridge.pickList("anim", index) }
                    }
                }
                Text { text: "Play"; color: "#ff5a1f"; font.pixelSize: 12; font.bold: true; TapHandler { onTapped: bridge.clickId("play") } }
                Slide { key: "frame"; lab: "Frame"; min: 0; max: Math.max(1, side.bag.frameMax || 1); val: side.bag.frame || 0 }
            }

            Column {
                width: parent.width
                spacing: 4
                visible: side.bag.tab === 4
                Text { text: "Lighting & scene"; color: side.ink; font.pixelSize: 13; font.bold: true }
                Flow {
                    width: parent.width
                    spacing: 4
                    Repeater {
                        model: (side.bag.env && side.bag.env.items) || []
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: elab.implicitWidth + 12
                            height: 26
                            radius: 8
                            color: index === side.bag.env.i ? "#ff5a1f" : "transparent"
                            Text { id: elab; anchors.centerIn: parent; text: modelData; color: index === side.bag.env.i ? "#fff" : side.ink; font.pixelSize: 11 }
                            TapHandler { onTapped: bridge.setCombo("env", index) }
                        }
                    }
                }
                Text {
                    text: side.bag.ground ? "☑ Ground plane" : "☐ Ground plane"
                    color: side.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("ground", !side.bag.ground) }
                }
                Text { text: "Reset camera"; color: "#ff5a1f"; font.pixelSize: 12; TapHandler { onTapped: bridge.clickId("resetCam") } }
                Text {
                    text: side.bag.sun ? "☑ Sun mode" : "☐ Sun mode"
                    color: side.ink
                    font.pixelSize: 12
                    TapHandler { onTapped: bridge.setChecked("sun", !side.bag.sun) }
                }
                Slide { key: "az"; lab: side.bag.azLab || ""; min: 0; max: 360; val: side.bag.az || 0 }
                Slide { key: "el"; lab: side.bag.elLab || ""; min: -10; max: 89; val: side.bag.el || 0 }
                Slide { key: "sunInt"; lab: side.bag.intLab || ""; min: 20; max: 500; val: side.bag.sunInt || 20 }
                Repeater {
                    model: side.bag.lights || []
                    delegate: Text {
                        required property var modelData
                        required property int index
                        text: (modelData.on ? "☑ " : "☐ ") + modelData.t
                        color: side.ink
                        font.pixelSize: 12
                        TapHandler { onTapped: bridge.setChecked("light" + index, !modelData.on) }
                    }
                }
                Slide { key: "emis"; lab: side.bag.emisLab || ""; min: 0; max: 200; val: side.bag.emis || 0 }
            }
        }
    }

    Row {
        id: foot
        anchors.bottom: parent.bottom
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8
        RaiseButton {
            width: 40
            height: 40
            accent: true
            glyph: bridge.openGlyph || "●"
            fontName: bridge.iconFont
            tip: "Open"
            onClicked: bridge.clickId("open")
        }
        RaiseButton {
            width: 40
            height: 40
            glyph: bridge.folderGlyph || "●"
            fontName: bridge.iconFont
            tip: "Folder"
            onClicked: bridge.clickId("folder")
        }
    }

    component Slide: Item {
        property string key: ""
        property string lab: ""
        property int min: 0
        property int max: 1
        property int val: 0
        width: body.width
        height: 32
        Text { text: lab; color: side.mute; font.pixelSize: 11; anchors.left: parent.left; anchors.top: parent.top }
        Rectangle {
            id: track
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 6
            radius: 3
            color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.45)
            Rectangle {
                width: Math.max(6, track.width * side.slide(key, min, max, val))
                height: parent.height
                radius: 3
                color: "#ff5a1f"
            }
            MouseArea {
                anchors.fill: parent
                anchors.margins: -8
                onPressed: bridge.setSlider(key, Math.round(min + Math.max(0, Math.min(1, mouse.x / track.width)) * (max - min)))
                onPositionChanged: if (pressed) bridge.setSlider(key, Math.round(min + Math.max(0, Math.min(1, mouse.x / track.width)) * (max - min)))
            }
        }
    }
}
