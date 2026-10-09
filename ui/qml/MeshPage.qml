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
        add(loadCard)
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

    Connections {
        target: bridge
        function onChanged() {
            if (pieLatch.open === bridge.pieOpen)
                return
            pieLatch.open = bridge.pieOpen
            root.publish()
        }
    }

    QtObject {
        id: pieLatch
        property bool open: false
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
    DropZone {
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
            veil: 0.72
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
        x: (bridge.editorOpen && !bridge.settingsOpen && (bridge.page === "meshes" || bridge.page === "attachs")) ? (parent.width - width - root.margin) : (parent.width + 8)
        visible: bridge.mesh && !bridge.settingsOpen && (bridge.page === "meshes" || bridge.page === "attachs")
        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 16
            foot: 10
            veil: 0.72
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
                text: (typeof bridge.welcomeTitle === "string" ? qsTr(bridge.welcomeTitle) : bridge.welcomeTitle)
                color: root.ink
                font.pixelSize: 28
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                width: parent.width
                text: (typeof bridge.welcomeBody === "string" ? qsTr(bridge.welcomeBody) : bridge.welcomeBody)
                color: root.mute
                font.pixelSize: 13
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            RaiseButton {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 240
                height: 44
                label: (typeof bridge.openLabel === "string" ? qsTr(bridge.openLabel) : bridge.openLabel)
                accent: true
                onClicked: bridge.browse()
            }
            RaiseButton {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 240
                height: 40
                label: (typeof bridge.fixtureLabel === "string" ? qsTr(bridge.fixtureLabel) : bridge.fixtureLabel)
                onClicked: bridge.openFixture()
            }
            RaiseButton {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 240
                height: 36
                label: (typeof bridge.homeLabel === "string" ? qsTr(bridge.homeLabel) : bridge.homeLabel)
                onClicked: bridge.goHome()
            }
            Text {
                width: parent.width
                text: (typeof bridge.tip === "string" ? qsTr(bridge.tip) : bridge.tip)
                color: root.mute
                font.pixelSize: 11
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
            }
            Text {
                width: parent.width
                text: (typeof bridge.copy === "string" ? qsTr(bridge.copy) : bridge.copy)
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
                        text: (typeof modelData === "string" ? qsTr(modelData) : modelData)
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
        text: (typeof bridge.shortcut === "string" ? qsTr(bridge.shortcut) : bridge.shortcut)
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
            text: (typeof bridge.bakeStage === "string" ? qsTr(bridge.bakeStage) : bridge.bakeStage)
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
                text: (typeof bridge.closeGlyph === "string" ? qsTr(bridge.closeGlyph) : bridge.closeGlyph)
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
            text: (typeof bridge.bakeEta === "string" ? qsTr(bridge.bakeEta) : bridge.bakeEta)
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
                    text: (typeof bridge.homeGlyph === "string" ? qsTr(bridge.homeGlyph) : bridge.homeGlyph)
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
        function sync() {
            var hit = null
            for (var i = 0; i < chipRow.children.length; ++i) {
                var chip = chipRow.children[i]
                if (chip.hot)
                    hit = chip
            }
            if (hit)
                stick(hit)
            else
                pillW = 0
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
        onHotChanged: if (well) well.sync()
        onXChanged: if (hot && well) well.sync()
        onWidthChanged: if (hot && well) well.sync()
        Component.onCompleted: if (well) well.sync()
        Text {
            id: chipText
            z: 2
            anchors.centerIn: parent
            anchors.verticalCenterOffset: chipTap.pressed ? 1 : 0
            text: (typeof label === "string" ? qsTr(label) : label)
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

    Item {
        id: loadSheet
        anchors.fill: parent
        z: 80
        visible: bridge.loadOpen
        onVisibleChanged: root.publish()

        Rectangle {
            anchors.fill: parent
            color: bridge.dark ? "#c0101418" : "#d4eef1f6"
        }

        GlassPlate {
            id: loadCard
            anchors.centerIn: parent
            width: Math.min(440, parent.width - 48)
            height: 188
            dark: bridge.dark
            plateRadius: 18

            Column {
                anchors.fill: parent
                anchors.margins: 22
                spacing: 8

                Text {
                    width: parent.width
                    text: qsTr("Opening mesh")
                    color: bridge.dark ? "#f2f3f5" : "#1d1d1f"
                    font.pixelSize: 16
                    font.bold: true
                    elide: Text.ElideRight
                }
                Text {
                    width: parent.width
                    text: (typeof bridge.loadName === "string" ? qsTr(bridge.loadName) : bridge.loadName)
                    color: bridge.dark ? "#a8b0bc" : "#5c6570"
                    font.pixelSize: 12
                    elide: Text.ElideMiddle
                }
                Text {
                    width: parent.width
                    text: (typeof bridge.loadStage === "string" ? qsTr(bridge.loadStage) : bridge.loadStage)
                    color: root.ink
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Rectangle {
                    width: parent.width
                    height: 8
                    radius: 4
                    color: bridge.dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.08)
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(100, bridge.loadPct)) / 100
                        height: parent.height
                        radius: 4
                        color: "#ff5a1f"
                    }
                }
                Text {
                    text: bridge.loadPct + "%"
                    color: bridge.dark ? "#8b93a1" : "#5c6570"
                    font.pixelSize: 11
                }
            }
        }
    }

    Item {
        id: pie
        anchors.fill: parent
        z: 40
        visible: bridge.pieOpen || reveal > 0.02
        property real reveal: 0
        property bool tracking: false
        property bool closing: false
        property real spin: 0
        property real aimX: 0
        property real aimY: 0
        property var pops: [0, 0, 0, 0]
        readonly property real wheelScale: closing ? (0.55 + 0.45 * Math.max(0, reveal)) : (0.72 + 0.28 * Math.min(1.15, reveal))

        function popAt(i) {
            if (!pops || i < 0 || i >= pops.length)
                return 0
            return pops[i]
        }

        NumberAnimation {
            id: openAnim
            target: pie
            property: "reveal"
            to: 1
            duration: 340
            easing.type: Easing.OutBack
            easing.overshoot: 1.45
        }
        NumberAnimation {
            id: closeAnim
            target: pie
            property: "reveal"
            to: 0
            duration: 220
            easing.type: Easing.InCubic
        }

        Timer {
            interval: 16
            repeat: true
            running: pie.visible
            onTriggered: {
                pie.spin += 0.016
                var n = bridge.pieLabels.length
                var next = []
                for (var i = 0; i < n; ++i) {
                    var cur = pie.popAt(i)
                    var goal = i === bridge.pieHover ? 1 : 0
                    next.push(cur + (goal - cur) * 0.28)
                }
                pie.pops = next
                wheel.requestPaint()
            }
        }

        Canvas {
            id: wheel
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.clearRect(0, 0, width, height)
                var reveal = pie.reveal
                if (reveal < 0.02)
                    return
                var alpha = Math.min(1, reveal)
                var labels = bridge.pieLabels
                var n = Math.max(1, labels.length)
                var cx = bridge.pieX
                var cy = bridge.pieY
                var scale = pie.wheelScale
                var veil = ctx.createRadialGradient(cx, cy, 30, cx, cy, Math.max(width, height) * 0.72)
                veil.addColorStop(0, Qt.rgba(0.03, 0.05, 0.07, 0.12 * alpha))
                veil.addColorStop(1, Qt.rgba(0, 0, 0, 0.55 * alpha))
                ctx.fillStyle = veil
                ctx.fillRect(0, 0, width, height)

                ctx.save()
                ctx.translate(cx, cy)
                ctx.scale(scale, scale)
                ctx.translate(-cx, -cy)

                var rOut = 124
                var rIn = 40
                var sector = Math.PI * 2 / n
                var gap = Math.min(0.09, sector * 0.08)
                var halo = ctx.createRadialGradient(cx, cy, rOut * 0.55, cx, cy, rOut + 36)
                halo.addColorStop(0, Qt.rgba(1, 1, 1, 0))
                halo.addColorStop(0.78, Qt.rgba(1, 1, 1, 0.10 * alpha))
                halo.addColorStop(0.92, Qt.rgba(1, 0.45, 0.2, 0.28 * alpha))
                halo.addColorStop(1, Qt.rgba(1, 0.35, 0.12, 0))
                ctx.fillStyle = halo
                ctx.beginPath()
                ctx.arc(cx, cy, rOut + 36, 0, Math.PI * 2)
                ctx.fill()

                var t = pie.spin
                for (var b = 0; b < 12; ++b) {
                    var drift = 0.55 + (b % 3) * 0.22
                    var bang = (b / 12) * Math.PI * 2 + (b % 2 ? 0.35 : 0) + t * 0.35 * drift
                    var bob = Math.sin(t * 1.7 + b * 0.73) * 6 + Math.cos(t * 1.1 + b) * 4
                    var orbit = rOut + 18 + (b % 4) * 14 + bob
                    var bx = cx + Math.cos(bang) * orbit
                    var by = cy + Math.sin(bang) * orbit
                    var rs = (4 + (b % 5) * 2.2) * (0.85 + 0.15 * Math.sin(t * 2.4 + b))
                    var bubble = ctx.createRadialGradient(bx - rs * 0.25, by - rs * 0.3, 0, bx, by, rs * 1.35)
                    bubble.addColorStop(0, Qt.rgba(1, 1, 1, 0.42 * alpha))
                    bubble.addColorStop(0.5, Qt.rgba(1, 0.72, 0.5, 0.18 * alpha))
                    bubble.addColorStop(1, Qt.rgba(1, 0.35, 0.12, 0))
                    ctx.fillStyle = bubble
                    ctx.beginPath()
                    ctx.arc(bx, by, rs, 0, Math.PI * 2)
                    ctx.fill()
                }

                for (var i = 0; i < n; ++i) {
                    var hot = pie.popAt(i)
                    var mid = -Math.PI / 2 + i * sector
                    var a0 = mid - sector / 2 + gap
                    var a1 = mid + sector / 2 - gap
                    var ro = rOut + hot * 14
                    ctx.beginPath()
                    ctx.arc(cx, cy, ro, a0, a1, true)
                    ctx.arc(cx, cy, rIn + 2, a1, a0, false)
                    ctx.closePath()
                    var fill = ctx.createLinearGradient(cx, cy - ro, cx, cy + ro)
                    fill.addColorStop(0, Qt.rgba(1, 0.82, 0.7, (0.16 + 0.20 * hot) * alpha))
                    fill.addColorStop(0.4, Qt.rgba(1, 0.42, 0.16, (0.10 + 0.38 * hot) * alpha))
                    fill.addColorStop(1, Qt.rgba(0.12 + 0.55 * hot, 0.10, 0.08, (0.55 + 0.25 * hot) * alpha))
                    ctx.fillStyle = fill
                    ctx.fill()
                    ctx.save()
                    ctx.clip()
                    var sheen = ctx.createRadialGradient(cx - ro * 0.15, cy - ro * 0.35, 4, cx, cy, ro)
                    sheen.addColorStop(0, Qt.rgba(1, 1, 1, (0.10 + 0.16 * hot) * alpha))
                    sheen.addColorStop(0.6, Qt.rgba(1, 1, 1, 0))
                    ctx.fillStyle = sheen
                    ctx.fillRect(cx - ro, cy - ro, ro * 2, ro * 2)
                    ctx.restore()
                    ctx.beginPath()
                    ctx.arc(cx, cy, ro, a0, a1, true)
                    ctx.arc(cx, cy, rIn + 2, a1, a0, false)
                    ctx.closePath()
                    ctx.strokeStyle = Qt.rgba(1, 0.9 - 0.15 * (1 - hot), 0.75, (0.22 + 0.5 * hot) * alpha)
                    ctx.lineWidth = 1 + hot
                    ctx.stroke()
                }

                var dx = (pie.aimX - cx) / Math.max(0.2, scale)
                var dy = (pie.aimY - cy) / Math.max(0.2, scale)
                var len = Math.sqrt(dx * dx + dy * dy)
                if (len > 28) {
                    var end = Math.min(len, rOut + 6)
                    ctx.beginPath()
                    ctx.moveTo(cx + dx / len * (rIn + 8), cy + dy / len * (rIn + 8))
                    ctx.lineTo(cx + dx / len * end, cy + dy / len * end)
                    ctx.strokeStyle = Qt.rgba(1, 0.86, 0.72, 0.55 * alpha)
                    ctx.lineWidth = 2
                    ctx.stroke()
                }

                var hub = ctx.createRadialGradient(cx, cy - rIn * 0.25, 4, cx, cy, rIn * 1.15)
                hub.addColorStop(0, Qt.rgba(1, 1, 1, 0.28 * alpha))
                hub.addColorStop(0.45, Qt.rgba(0.16, 0.19, 0.23, 0.7 * alpha))
                hub.addColorStop(1, Qt.rgba(0.06, 0.08, 0.11, 0.9 * alpha))
                ctx.beginPath()
                ctx.arc(cx, cy, rIn, 0, Math.PI * 2)
                ctx.fillStyle = hub
                ctx.fill()
                ctx.strokeStyle = Qt.rgba(1, 0.62, 0.38, 0.75 * alpha)
                ctx.lineWidth = 1.6
                ctx.stroke()
                ctx.beginPath()
                ctx.arc(cx, cy, rIn - 6, -2.4, -0.7, false)
                ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.35 * alpha)
                ctx.lineWidth = 1.2
                ctx.stroke()
                ctx.restore()
            }
        }

        Item {
            anchors.fill: parent
            transform: Scale {
                origin.x: bridge.pieX
                origin.y: bridge.pieY
                xScale: pie.wheelScale
                yScale: pie.wheelScale
            }

            Repeater {
                model: bridge.pieLabels
                delegate: Text {
                    required property string modelData
                    required property int index
                    property real ang: -Math.PI / 2 + index * (Math.PI * 2 / Math.max(1, bridge.pieLabels.length))
                    property real hot: pie.popAt(index)
                    property real reach: 86 + hot * 16
                    x: bridge.pieX + Math.cos(ang) * reach - width / 2
                    y: bridge.pieY + Math.sin(ang) * reach - height / 2
                    text: (typeof modelData === "string" ? qsTr(modelData) : modelData)
                    color: Qt.rgba(1, 1, 1, 0.62 + 0.38 * hot)
                    font.pixelSize: 13 + hot * 3
                    font.bold: hot > 0.45
                    scale: 0.92 + hot * 0.12
                }
            }

            Text {
                x: bridge.pieX - width / 2
                y: bridge.pieY - height / 2
                text: (typeof bridge.pieTitle === "string" ? qsTr(bridge.pieTitle) : bridge.pieTitle)
                color: "#ff8c50"
                opacity: Math.min(1, pie.reveal)
                font.pixelSize: 12
                font.bold: true
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: bridge.pieOpen
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onPositionChanged: function (mouse) {
                pie.aimX = mouse.x
                pie.aimY = mouse.y
                bridge.pieHoverAt(mouse.x, mouse.y)
            }
            onPressed: function (mouse) {
                pie.aimX = mouse.x
                pie.aimY = mouse.y
                bridge.pieHoverAt(mouse.x, mouse.y)
                if (mouse.button === Qt.RightButton)
                    bridge.cancelPie()
                else
                    bridge.commitPie()
            }
        }

        onRevealChanged: wheel.requestPaint()
        Connections {
            target: bridge
            function onChanged() {
                if (bridge.pieOpen && !pie.tracking) {
                    pie.tracking = true
                    pie.closing = false
                    pie.aimX = bridge.pieX
                    pie.aimY = bridge.pieY
                    closeAnim.stop()
                    openAnim.start()
                } else if (!bridge.pieOpen && pie.tracking) {
                    pie.tracking = false
                    pie.closing = true
                    openAnim.stop()
                    closeAnim.start()
                }
                wheel.requestPaint()
            }
        }
    }
}
