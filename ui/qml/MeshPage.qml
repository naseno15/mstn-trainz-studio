import QtQuick

// Mesh Studio chrome. The viewport is the unmasked center (MeshView stays under this page).
// Sidebar, editor, and settings widgets are placed into the glass plates.
Item {
    id: root

    readonly property real margin: 10
    readonly property real sideW: Math.min(420, Math.max(260, width / 4))
    readonly property real clearMin: Math.max(280, width * 0.40)
    readonly property real editorW: {
        var sideTake = bridge.sideOpen ? (sideW + margin) : 0
        return Math.min(480, Math.max(260, width - sideTake - clearMin - margin))
    }
    readonly property color ink: bridge.dark ? "#f4f6fa" : "#1c1c1e"
    readonly property color mute: bridge.dark ? "#9aa3b2" : "#5c6570"

    function chromeRects() {
        var out = []
        function add(it) {
            if (!it || !it.visible || it.width < 2 || it.height < 2)
                return
            var o = it.mapToItem(root, 0, 0)
            out.push(o.x, o.y, it.width, it.height)
        }
        if (bridge.welcome && bridge.mesh)
            out.push(0, 0, width, height)
        add(sidePlate)
        add(editorPlate)
        add(settingsPlate)
        add(nav)
        add(hud)
        add(bake)
        add(shortcut)
        return out
    }

    function publish() {
        bridge.noteChrome(chromeRects())
    }

    onWidthChanged: publish()
    onHeightChanged: publish()
    Component.onCompleted: publish()

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    Rectangle {
        anchors.fill: parent
        visible: bridge.mesh && bridge.welcome
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1a2230" : "#eef1f6" }
            GradientStop { position: 1.0; color: bridge.dark ? "#0c0e12" : "#d5dbe3" }
        }
    }

    // Welcome paints a full-page mask, so file drops land here — not on the window.
    DropArea {
        anchors.fill: parent
        z: 1
        onDropped: function (drop) {
            var urls = []
            if (drop.hasUrls) {
                for (var i = 0; i < drop.urls.length; ++i)
                    urls.push(String(drop.urls[i]))
            }
            if (urls.length > 0)
                bridge.dropUrls(urls)
            drop.acceptProposedAction()
        }
    }

    Item {
        id: sidePlate
        y: root.margin
        width: root.sideW
        height: Math.max(1, parent.height - root.margin * 2)
        x: bridge.sideOpen ? root.margin : -width - 8
        visible: bridge.mesh && !bridge.settingsOpen
        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 16
            foot: 10
            MeshSide { anchors.fill: parent }
        }
        function sync() {
            var p = mapToItem(root, 0, 0)
            bridge.placeSide(p.x, p.y, width, height)
            root.publish()
        }
        onXChanged: sync()
        onYChanged: sync()
        onWidthChanged: sync()
        onHeightChanged: sync()
        onVisibleChanged: sync()
    }

    Item {
        id: editorPlate
        y: root.margin
        width: root.editorW
        height: Math.max(1, parent.height - root.margin * 2)
        x: (bridge.editorOpen && !bridge.settingsOpen) ? (parent.width - width - root.margin) : (parent.width + 8)
        visible: bridge.mesh && !bridge.settingsOpen
        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 16
            foot: 10
            MeshDock { anchors.fill: parent }
        }
        function sync() {
            var p = mapToItem(root, 0, 0)
            bridge.placeEditor(p.x, p.y, width, height)
            root.publish()
        }
        onXChanged: sync()
        onYChanged: sync()
        onWidthChanged: sync()
        onHeightChanged: sync()
        onVisibleChanged: sync()
    }

    Item {
        id: settingsPlate
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: nav.top
        anchors.bottomMargin: 8
        visible: bridge.mesh && bridge.settingsOpen
        GlassPlate {
            anchors.fill: parent
            anchors.margins: 10
            dark: bridge.dark
            plateRadius: 16
            foot: 10
        }
        function sync() {
            if (!visible) {
                bridge.placeSettings(0, 0, 0, 0)
                root.publish()
                return
            }
            var p = mapToItem(root, 10, 10)
            bridge.placeSettings(p.x, p.y, Math.max(0, width - 20), Math.max(0, height - 20))
            root.publish()
        }
        onXChanged: sync()
        onYChanged: sync()
        onWidthChanged: sync()
        onHeightChanged: sync()
        onVisibleChanged: sync()
    }

    Item {
        id: welcomeCard
        visible: bridge.mesh && bridge.welcome && !bridge.settingsOpen
        x: Math.max(0, sidePlate.x + sidePlate.width)
        width: Math.max(220, Math.min(parent.width, editorPlate.x) - x)
        y: 24
        height: Math.max(120, nav.y - 36)
        z: 4

        Column {
            anchors.centerIn: parent
            width: Math.min(520, parent.width - 24)
            spacing: 12

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "image://mstnlogo/" + (bridge.dark ? "dark" : "light")
                width: 180
                height: 72
                fillMode: Image.PreserveAspectFit
            }
            Text {
                width: parent.width
                text: bridge.welcomeTitle
                color: root.ink
                font.pixelSize: 28
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                width: parent.width
                text: bridge.welcomeBody
                color: root.mute
                font.pixelSize: 13
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            RaiseButton {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 240
                height: 44
                label: bridge.openLabel
                accent: true
                onClicked: bridge.browse()
            }
            RaiseButton {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 240
                height: 40
                label: bridge.fixtureLabel
                onClicked: bridge.openFixture()
            }
            RaiseButton {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 240
                height: 36
                label: bridge.homeLabel
                onClicked: bridge.goHome()
            }
            Text {
                width: parent.width
                text: bridge.tip
                color: root.mute
                font.pixelSize: 11
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                width: parent.width
                text: bridge.copy
                color: root.mute
                font.pixelSize: 11
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Item {
        id: hud
        visible: bridge.mesh && bridge.pbrOn && !bridge.welcome
        z: 6
        height: 56
        y: 8
        readonly property real laneL: Math.max(0, sidePlate.x + sidePlate.width + 8)
        readonly property real laneR: Math.min(parent.width, editorPlate.x) - 8
        width: Math.min(Math.max(280, row.implicitWidth + 16), Math.max(280, laneR - laneL))
        x: laneL + Math.max(0, (laneR - laneL - width) / 2)

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 22
            foot: 8
        }
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 2
            Repeater {
                model: bridge.pbrLabels
                delegate: Item {
                    required property string modelData
                    required property int index
                    width: Math.max(58, lab.implicitWidth + 16)
                    height: 34
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 1
                        radius: 10
                        color: index === bridge.pbr ? "#ff5a1f" : "transparent"
                    }
                    Text {
                        id: lab
                        anchors.centerIn: parent
                        text: modelData
                        color: index === bridge.pbr ? "#ffffff" : root.ink
                        font.pixelSize: 12
                        font.bold: index === bridge.pbr
                    }
                    TapHandler { onTapped: bridge.setPbr(index) }
                }
            }
        }
        onXChanged: root.publish()
        onYChanged: root.publish()
        onWidthChanged: root.publish()
        onVisibleChanged: root.publish()
    }

    Text {
        id: shortcut
        visible: bridge.mesh && !bridge.bakeOn && text.length > 0
        z: 6
        text: bridge.shortcut
        color: root.mute
        font.pixelSize: 11
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        readonly property real laneL: Math.max(8, sidePlate.x + sidePlate.width + 8)
        readonly property real laneR: Math.min(parent.width - 8, editorPlate.x - 8)
        x: laneL
        width: Math.max(80, laneR - laneL)
        y: nav.y - height - 6
        onXChanged: root.publish()
        onYChanged: root.publish()
        onWidthChanged: root.publish()
        onVisibleChanged: root.publish()
    }

    Item {
        id: bake
        visible: bridge.mesh && bridge.bakeOn
        z: 8
        height: 56
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(720, Math.max(280, parent.width - 48))

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 22
            foot: 8
        }
        Text {
            id: bakeStage
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            text: bridge.bakeStage
            color: root.ink
            font.pixelSize: 13
            font.bold: true
        }
        Item {
            id: bakeCancel
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            width: 32
            height: 32
            Text {
                anchors.centerIn: parent
                text: bridge.closeGlyph
                font.family: mi.name.length > 0 ? mi.name : bridge.iconFont
                font.pixelSize: 18
                color: root.ink
            }
            TapHandler { onTapped: bridge.cancelBake() }
        }
        Text {
            id: bakeEta
            anchors.right: bakeCancel.left
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: bridge.bakeEta
            color: root.mute
            font.pixelSize: 12
        }
        Text {
            id: bakePct
            anchors.right: bakeEta.left
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: bridge.bakePct + "%"
            color: root.ink
            font.pixelSize: 12
        }
        Rectangle {
            anchors.left: bakeStage.right
            anchors.right: bakePct.left
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            height: 8
            radius: 4
            color: Qt.rgba(1, 1, 1, bridge.dark ? 0.12 : 0.45)
            Rectangle {
                width: parent.width * Math.max(0, Math.min(100, bridge.bakePct)) / 100
                height: parent.height
                radius: 4
                color: "#ff5a1f"
            }
        }
        onVisibleChanged: root.publish()
        onXChanged: root.publish()
        onWidthChanged: root.publish()
    }

    Item {
        id: nav
        visible: bridge.mesh && !bridge.bakeOn
        z: 8
        height: 88
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        readonly property real laneL: Math.max(8, sidePlate.x + sidePlate.width + 8)
        readonly property real laneR: Math.min(parent.width - 8, editorPlate.x - 8)
        width: Math.min(Math.max(360, cluster.width + 28), Math.max(360, laneR - laneL))
        x: laneL + Math.max(0, (laneR - laneL - width) / 2)

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 28
            foot: 10
        }

        Row {
            id: cluster
            anchors.centerIn: parent
            spacing: 8
            height: 48

            ChipWell {
                id: leftWell
                NavChip { key: "preview"; label: bridge.preview; hot: bridge.page === "preview"; well: leftWell }
                NavChip { key: "meshes"; label: bridge.meshes; hot: bridge.page === "meshes"; well: leftWell }
            }
            Item {
                id: homeKey
                width: 48
                height: 48
                property real sink: homeTap.pressed ? 1 : 0
                Behavior on sink { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                Repeater {
                    model: 3
                    delegate: Rectangle {
                        required property int index
                        property real t: (index + 1) / 3
                        anchors.fill: parent
                        anchors.topMargin: 2 + index + homeKey.sink * 2
                        anchors.bottomMargin: -t * 3 * (1 - homeKey.sink)
                        radius: 16
                        opacity: 1 - homeKey.sink
                        color: Qt.rgba(0, 0, 0, 0.18 * (1.05 - t))
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: homeKey.sink * 3
                    anchors.bottomMargin: 3 * (1 - homeKey.sink)
                    radius: 16
                    color: homeH.hovered ? Qt.rgba(1, 0.35, 0.16, 0.35) : (bridge.dark ? Qt.rgba(0.22, 0.24, 0.28, 0.96) : Qt.rgba(0.94, 0.95, 0.97, 0.96))
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.55)
                }
                Text {
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: homeKey.sink
                    text: bridge.homeGlyph
                    font.family: mi.name.length > 0 ? mi.name : bridge.iconFont
                    font.pixelSize: 22
                    color: homeH.hovered ? "#ff5a1f" : root.ink
                }
                HoverHandler { id: homeH }
                TapHandler {
                    id: homeTap
                    onTapped: bridge.goHome()
                }
            }
            ChipWell {
                id: rightWell
                NavChip { key: "attachs"; label: bridge.attachs; hot: bridge.page === "attachs"; well: rightWell }
                NavChip { key: "settings"; label: bridge.settingsLabel; hot: bridge.page === "settings"; well: rightWell }
            }
        }
        onXChanged: root.publish()
        onYChanged: root.publish()
        onWidthChanged: root.publish()
        onVisibleChanged: root.publish()
    }

    component ChipWell: Item {
        id: well
        default property alias chips: chipRow.data
        property real sink: 0
        property real pillX: 4
        property real pillW: 0
        width: chipRow.width
        height: 48
        Behavior on sink { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        Behavior on pillX { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
        Behavior on pillW { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }

        Rectangle {
            anchors.fill: parent
            radius: 16
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
        }
        Item {
            z: 1
            visible: well.pillW > 8
            x: well.pillX
            y: 6 + well.sink * 2
            width: well.pillW
            height: 36 - well.sink * 2
            Repeater {
                model: 3
                delegate: Rectangle {
                    required property int index
                    property real t: (index + 1) / 3
                    anchors.fill: parent
                    anchors.leftMargin: 1 - t * 2
                    anchors.rightMargin: 1 - t * 2
                    anchors.topMargin: 1 + index
                    anchors.bottomMargin: -t * 2 * (1 - well.sink)
                    radius: 12
                    opacity: 1 - well.sink
                    color: Qt.rgba(0, 0, 0, 0.22 * (1.05 - t))
                }
            }
            Rectangle {
                anchors.fill: parent
                anchors.topMargin: well.sink * 2
                anchors.bottomMargin: 2 * (1 - well.sink)
                radius: 12
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#ff7a45" }
                    GradientStop { position: 0.42; color: "#ff5a1f" }
                    GradientStop { position: 1.0; color: "#c43a10" }
                }
            }
        }

        Row { id: chipRow; z: 2 }

        function stick(item) {
            pillX = item.x + 4
            pillW = Math.max(0, item.width - 8)
        }
    }

    component NavChip: Item {
        id: chip
        property string key: ""
        property string label: ""
        property bool hot: false
        property Item well: null
        width: Math.max(108, chipText.implicitWidth + 28)
        height: 48
        onHotChanged: if (hot && well) well.stick(chip)
        onXChanged: if (hot && well) well.stick(chip)
        onWidthChanged: if (hot && well) well.stick(chip)
        Component.onCompleted: if (hot && well) well.stick(chip)
        Text {
            id: chipText
            z: 2
            anchors.centerIn: parent
            anchors.verticalCenterOffset: chipTap.pressed ? 1 : 0
            text: label
            color: hot ? "#ffffff" : root.ink
            font.pixelSize: 13
            font.bold: hot
        }
        HoverHandler { id: chipH }
        Rectangle {
            z: 0
            anchors.fill: parent
            anchors.margins: 6
            radius: 12
            visible: !hot
            color: chipH.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent"
        }
        TapHandler {
            id: chipTap
            onPressedChanged: if (well) well.sink = pressed ? 1 : 0
            onTapped: bridge.setPage(key)
        }
    }
}
