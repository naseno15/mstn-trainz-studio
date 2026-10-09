import QtQuick

// Left Mesh Studio sidebar. Lists and controls call the hidden widgets.
// Chrome matches Engine Tuner Auto Tune: cards, chips, checks, raised actions.
Item {
    id: side

    readonly property var bag: {
        try { return JSON.parse(bridge.sideJson) } catch (e) { return {} }
    }
    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    readonly property color line: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
    readonly property color well: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)

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
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Mesh Studio"
            color: side.ink
            font.pixelSize: 15
            font.bold: true
        }
        Item {
            id: tabWell
            width: parent.width
            height: 40
            readonly property int count: Math.max(1, (side.bag.tabs || []).length)

            Rectangle {
                anchors.fill: parent
                radius: 14
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: side.line
            }
            Rectangle {
                id: tabPill
                y: 4
                height: 32
                radius: 11
                width: (tabWell.width - 8) / tabWell.count
                x: 4 + (side.bag.tab || 0) * width
                color: "#ff5a1f"
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    anchors.topMargin: 1
                    height: 1
                    color: Qt.rgba(1, 1, 1, 0.55)
                }
                Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
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
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: bridge.setSideTab(index) }
                    }
                }
            }
        }
    }

    Flickable {
        id: scroller
        anchors.top: head.bottom
        anchors.topMargin: 10
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: foot.top
        anchors.bottomMargin: 10
        contentWidth: width
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: body
            width: scroller.width
            spacing: 10

            Card {
                title: ""
                Column {
                    width: parent.width
                    spacing: 6
                    Item {
                        width: parent.width
                        height: 22
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: (side.bag.infoOpen ? "▾  " : "▸  ") + "Mesh Info"
                            color: side.ink
                            font.pixelSize: 13
                            font.bold: true
                        }
                        TapHandler { onTapped: bridge.clickId("info") }
                    }
                    Column {
                        visible: side.bag.infoOpen === true
                        width: parent.width
                        spacing: 4
                        Repeater {
                            model: side.bag.stats || []
                            delegate: Item {
                                required property var modelData
                                width: parent.width
                                height: 18
                                Text {
                                    id: cap
                                    text: modelData.k
                                    color: side.mute
                                    font.pixelSize: 12
                                }
                                Text {
                                    anchors.left: cap.right
                                    anchors.right: parent.right
                                    anchors.leftMargin: 8
                                    text: modelData.v
                                    color: side.ink
                                    font.pixelSize: 12
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideLeft
                                }
                            }
                        }
                        Repeater {
                            model: side.bag.meshes || []
                            delegate: Row {
                                required property var modelData
                                required property int index
                                width: parent.width
                                height: 28
                                spacing: 6
                                CheckBox {
                                    y: 6
                                    on: modelData.show
                                    onToggled: bridge.toggleMesh(index, 0)
                                }
                                CheckBox {
                                    y: 6
                                    on: modelData.atts
                                    onToggled: bridge.toggleMesh(index, 1)
                                }
                                Text {
                                    text: modelData.name
                                    color: modelData.on ? "#ff5a1f" : side.ink
                                    font.pixelSize: 12
                                    font.bold: modelData.on
                                    width: parent.width - 44
                                    elide: Text.ElideRight
                                    anchors.verticalCenter: parent.verticalCenter
                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: bridge.pickList("mesh", index) }
                                }
                            }
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 10
                visible: side.bag.tab === 0

                Card {
                    title: side.bag.attTitle || "Attachments"
                    Text {
                        visible: (side.bag.cap || "").length > 0
                        width: parent.width
                        text: side.bag.cap || ""
                        color: side.mute
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                    Repeater {
                        model: side.bag.atts || []
                        delegate: PickRow {
                            required property string modelData
                            required property int index
                            label: modelData
                            on: index === side.bag.att
                            onPicked: bridge.pickList("atts", index)
                        }
                    }
                }

                Card {
                    title: "Scene"
                    visible: side.bag.showDs === true || (side.bag.sceneMeshes || []).length > 0 || side.bag.dsOn === true
                    CheckRow {
                        visible: side.bag.showDs === true
                        label: "Select all"
                        checked: side.bag.dsAll === true
                        onToggled: bridge.setChecked("dsAll", !side.bag.dsAll)
                    }
                    Repeater {
                        model: side.bag.sceneMeshes || []
                        delegate: Item {
                            required property var modelData
                            required property int index
                            width: parent.width
                            height: 28
                            CheckBox {
                                y: 6
                                on: modelData.ck === true
                                onToggled: bridge.toggleSceneMesh(index)
                            }
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 24
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.t
                                color: modelData.on ? "#ff5a1f" : side.ink
                                font.pixelSize: 12
                                elide: Text.ElideRight
                            }
                            TapHandler { onTapped: bridge.pickList("scene", index) }
                        }
                    }
                    RaiseButton {
                        visible: side.bag.dsOn === true
                        width: parent.width
                        height: 34
                        label: side.bag.dsLabel || "Apply"
                        accent: true
                        onClicked: bridge.clickId("dsApply")
                    }
                }

                Card {
                    title: "Viewport"
                    CheckRow {
                        label: "Face Orientation"
                        checked: side.bag.face === true
                        onToggled: bridge.setChecked("face", !side.bag.face)
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 10
                visible: side.bag.tab === 1
                Card {
                    title: "Texture view"
                    Flow {
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: (side.bag.tex && side.bag.tex.items) || []
                            delegate: Chip {
                                required property string modelData
                                required property int index
                                label: modelData
                                on: index === side.bag.tex.i
                                onPicked: bridge.setCombo("tex", index)
                            }
                        }
                    }
                }
                Card {
                    title: "Materials"
                    Repeater {
                        model: side.bag.mats || []
                        delegate: PickRow {
                            required property var modelData
                            required property int index
                            label: modelData.t + (modelData.a ? "   " + modelData.a : "")
                            on: modelData.on === true
                            indent: modelData.d * 14
                            onPicked: bridge.pickMat(index)
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 10
                visible: side.bag.tab === 2
                Card {
                    title: "Cabin glow"
                    CheckRow {
                        label: side.bag.moonLab || "Moon"
                        checked: side.bag.moon === true
                        onToggled: bridge.setChecked("moon", !side.bag.moon)
                    }
                    Slide { key: "moon"; lab: side.bag.moonLab || ""; min: 5; max: 120; val: side.bag.moonInt || 5 }
                }
                Card {
                    title: "Lamps"
                    Repeater {
                        model: side.bag.lamps || []
                        delegate: PickRow {
                            required property var modelData
                            required property int index
                            label: modelData.t
                            on: modelData.on === true
                            onPicked: bridge.pickList("lamp", index)
                        }
                    }
                    CheckRow {
                        label: "Glow + cast"
                        checked: side.bag.lampOn === true
                        onToggled: bridge.setChecked("lamp", !side.bag.lampOn)
                    }
                    Slide { key: "bright"; lab: side.bag.brightLab || ""; min: 0; max: 800; val: side.bag.bright || 0 }
                    Slide { key: "range"; lab: side.bag.rangeLab || ""; min: 5; max: 3000; val: side.bag.range || 5 }
                    RaiseButton {
                        width: parent.width
                        height: 34
                        label: "Color"
                        accent: true
                        onClicked: bridge.clickId("lampColor")
                    }
                    CheckRow {
                        label: "Lamp gizmos"
                        checked: side.bag.gizmo === true
                        onToggled: bridge.setChecked("gizmo", !side.bag.gizmo)
                    }
                    Row {
                        width: parent.width
                        spacing: 6
                        RaiseButton {
                            width: (parent.width - 12) / 3
                            height: 34
                            label: "Add"
                            onClicked: bridge.clickId("lampAdd")
                        }
                        RaiseButton {
                            width: (parent.width - 12) / 3
                            height: 34
                            label: "Remove"
                            onClicked: bridge.clickId("lampRemove")
                        }
                        RaiseButton {
                            width: (parent.width - 12) / 3
                            height: 34
                            label: "Rescan"
                            onClicked: bridge.clickId("lampRescan")
                        }
                    }
                }
                Card {
                    title: "Bake"
                    Flow {
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: (side.bag.bake && side.bag.bake.items) || []
                            delegate: Chip {
                                required property string modelData
                                required property int index
                                label: modelData
                                on: index === side.bag.bake.i
                                onPicked: bridge.setCombo("bake", index)
                            }
                        }
                    }
                    CheckRow {
                        label: "CUDA"
                        checked: side.bag.cuda === true
                        canUse: side.bag.cudaOn === true
                        onToggled: if (side.bag.cudaOn) bridge.setChecked("cuda", !side.bag.cuda)
                    }
                    RaiseButton {
                        width: parent.width
                        height: 36
                        label: "Bake lamps"
                        accent: true
                        onClicked: bridge.clickId("bake")
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 10
                visible: side.bag.tab === 3
                Card {
                    title: "Animations"
                    Text {
                        visible: side.bag.animEmpty === true
                        text: "No .kin beside this mesh"
                        color: side.mute
                        font.pixelSize: 12
                    }
                    Repeater {
                        model: side.bag.anims || []
                        delegate: PickRow {
                            required property string modelData
                            required property int index
                            label: modelData
                            on: index === side.bag.anim
                            onPicked: bridge.pickList("anim", index)
                        }
                    }
                    RaiseButton {
                        width: parent.width
                        height: 34
                        label: "Play"
                        accent: true
                        onClicked: bridge.clickId("play")
                    }
                    Slide { key: "frame"; lab: "Frame"; min: 0; max: Math.max(1, side.bag.frameMax || 1); val: side.bag.frame || 0 }
                }
            }

            Column {
                width: parent.width
                spacing: 10
                visible: side.bag.tab === 4
                Card {
                    title: "Environment"
                    Flow {
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: (side.bag.env && side.bag.env.items) || []
                            delegate: Chip {
                                required property string modelData
                                required property int index
                                label: modelData
                                on: index === side.bag.env.i
                                onPicked: bridge.setCombo("env", index)
                            }
                        }
                    }
                    CheckRow {
                        label: "Ground plane"
                        checked: side.bag.ground === true
                        onToggled: bridge.setChecked("ground", !side.bag.ground)
                    }
                    RaiseButton {
                        width: parent.width
                        height: 34
                        label: "Reset camera"
                        onClicked: bridge.clickId("resetCam")
                    }
                }
                Card {
                    title: "Sun"
                    CheckRow {
                        label: "Sun mode"
                        checked: side.bag.sun === true
                        onToggled: bridge.setChecked("sun", !side.bag.sun)
                    }
                    Slide { key: "az"; lab: side.bag.azLab || ""; min: 0; max: 360; val: side.bag.az || 0 }
                    Slide { key: "el"; lab: side.bag.elLab || ""; min: -10; max: 89; val: side.bag.el || 0 }
                    Slide { key: "sunInt"; lab: side.bag.intLab || ""; min: 20; max: 500; val: side.bag.sunInt || 20 }
                }
                Card {
                    title: "Lights"
                    Repeater {
                        model: side.bag.lights || []
                        delegate: CheckRow {
                            required property var modelData
                            required property int index
                            label: modelData.t
                            checked: modelData.on === true
                            onToggled: bridge.setChecked("light" + index, !modelData.on)
                        }
                    }
                    Slide { key: "emis"; lab: side.bag.emisLab || ""; min: 0; max: 200; val: side.bag.emis || 0 }
                }
            }
        }
    }

    Column {
        id: foot
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 6
        Rectangle {
            width: parent.width
            height: 1
            color: side.line
        }
        Text {
            text: "File"
            color: side.mute
            font.pixelSize: 11
        }
        Row {
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
    }

    component Card: Rectangle {
        property string title: ""
        default property alias body: inner.data
        width: parent ? parent.width : 0
        height: inner.height + 16
        radius: 12
        color: side.well
        border.width: 1
        border.color: side.line
        Column {
            id: inner
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 8
            spacing: 6
            Text {
                visible: title.length > 0
                text: title
                color: side.ink
                font.pixelSize: 13
                font.bold: true
            }
        }
    }

    component CheckBox: Rectangle {
        property bool on: false
        property bool hit: true
        signal toggled()
        width: 16
        height: 16
        radius: 4
        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.08)
        border.width: 1
        border.color: on ? "#ff5a1f" : side.line
        Rectangle {
            anchors.centerIn: parent
            width: 8
            height: 8
            radius: 2
            color: on ? "#ff5a1f" : "transparent"
        }
        HoverHandler { enabled: hit; cursorShape: Qt.PointingHandCursor }
        TapHandler { enabled: hit; onTapped: toggled() }
    }

    component CheckRow: Item {
        property string label: ""
        property bool checked: false
        property bool canUse: true
        signal toggled()
        width: parent ? parent.width : 0
        height: 22
        opacity: canUse ? 1 : 0.4
        CheckBox {
            y: 3
            on: checked
            hit: false
        }
        Text {
            anchors.left: parent.left
            anchors.leftMargin: 24
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: label
            color: side.ink
            font.pixelSize: 12
            elide: Text.ElideRight
        }
        TapHandler { onTapped: if (canUse) toggled() }
    }

    component Chip: Rectangle {
        property string label: ""
        property bool on: false
        signal picked()
        width: chipLab.implicitWidth + 16
        height: 28
        radius: 8
        color: on ? "#ff5a1f" : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.06)
        border.width: on ? 0 : 1
        border.color: side.line
        Text {
            id: chipLab
            anchors.centerIn: parent
            text: label
            color: on ? "#ffffff" : side.ink
            font.pixelSize: 11
            font.bold: on
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: picked() }
    }

    component PickRow: Rectangle {
        property string label: ""
        property bool on: false
        property int indent: 0
        signal picked()
        width: parent ? parent.width : 0
        height: 30
        radius: 8
        color: on ? "#ff5a1f" : "transparent"
        Text {
            x: 8 + indent
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - 8
            text: label
            color: on ? "#ffffff" : side.ink
            font.pixelSize: 12
            font.bold: on
            elide: Text.ElideRight
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: picked() }
    }

    component Slide: Item {
        property string key: ""
        property string lab: ""
        property int min: 0
        property int max: 1
        property int val: 0
        width: parent ? parent.width : 0
        height: 36
        Text {
            text: lab
            color: side.mute
            font.pixelSize: 11
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            elide: Text.ElideRight
        }
        Item {
            id: track
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 16
            readonly property real t: Math.max(0, Math.min(1, side.slide(key, min, max, val)))
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                height: 6
                radius: 3
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.10)
                border.width: 1
                border.color: side.line
            }
            Rectangle {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(6, track.width * track.t)
                height: 6
                radius: 3
                color: "#ff5a1f"
            }
            Rectangle {
                width: 14
                height: 14
                radius: 7
                anchors.verticalCenter: parent.verticalCenter
                x: Math.max(0, Math.min(track.width - width, track.width * track.t - width / 2))
                color: bridge.dark ? "#f4f6fa" : "#ffffff"
                border.width: 1
                border.color: "#ff5a1f"
            }
            MouseArea {
                anchors.fill: parent
                anchors.margins: -6
                cursorShape: Qt.PointingHandCursor
                onPressed: bridge.setSlider(key, Math.round(min + Math.max(0, Math.min(1, mouse.x / track.width)) * (max - min)))
                onPositionChanged: if (pressed) bridge.setSlider(key, Math.round(min + Math.max(0, Math.min(1, mouse.x / track.width)) * (max - min)))
            }
        }
    }
}
