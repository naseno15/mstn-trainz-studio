import QtQuick

// Tuner · Simulation · Parameters. TE graph is a QML Canvas in graphWell.
Item {
    id: center

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    property var bag: ({})
    property string raw: ""

    function readBag() {
        if (bridge.centerJson === raw)
            return
        raw = bridge.centerJson
        try {
            bag = JSON.parse(raw)
        } catch (e) {
            bag = ({})
        }
    }

    function pageRoot() {
        var item = center
        while (item.parent)
            item = item.parent
        return item
    }

    function numOr(text, fallback) {
        var n = parseFloat(String(text).replace(",", ""))
        return isFinite(n) ? n : fallback
    }

    Component.onCompleted: readBag()
    Connections {
        target: bridge
        function onChanged() { center.readBag() }
    }

    Text {
        id: pathLine
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        text: center.bag.path || ""
        color: center.mute
        font.pixelSize: 12
        elide: Text.ElideMiddle
    }

    TunerPage {
        anchors.top: pathLine.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: bridge.page === "tuner"
    }

    SimPage {
        anchors.top: pathLine.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: bridge.page === "simulation"
    }

    ParamsPage {
        anchors.top: pathLine.bottom
        anchors.topMargin: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: bridge.page === "parameters"
    }

    component Cell: TextInput {
        property string cell: ""
        signal commit(string text)
        text: (typeof cell === "string" ? qsTr(cell) : cell)
        color: center.ink
        font.pixelSize: 12
        selectByMouse: true
        horizontalAlignment: TextInput.AlignRight
        verticalAlignment: TextInput.AlignVCenter
        onEditingFinished: commit(text)
    }

    component TunerPage: Item {
        id: tuner

        function place() {
            if (!visible || graphWell.width < 2 || graphWell.height < 2)
                return
            var p = graphWell.mapToItem(center.pageRoot(), 0, 0)
            bridge.placeGraph(p.x, p.y, graphWell.width, graphWell.height)
        }

        onVisibleChanged: place()
        Component.onCompleted: place()

        Flickable {
            id: notchFlick
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: Math.max(150, tuner.height * 0.40)
            clip: true
            flickableDirection: Flickable.HorizontalFlick
            contentWidth: notchRow.width
            contentHeight: height

            Row {
                id: notchRow
                height: notchFlick.height
                spacing: 6

                Repeater {
                    model: center.bag.notches || []
                    delegate: Item {
                        id: col
                        width: 128
                        height: notchRow.height
                        required property var modelData
                        property int pick: -1

                        Rectangle {
                            anchors.fill: parent
                            radius: 12
                            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
                            border.width: bridge.notchFocus === col.modelData.n ? 2 : 1
                            border.color: bridge.notchFocus === col.modelData.n
                                         ? col.modelData.color
                                         : Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
                        }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 6
                            spacing: 4

                            Text {
                                width: parent.width
                                text: qsTr("N") + col.modelData.n
                                color: col.modelData.color
                                font.pixelSize: 13
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                            }
                            Row {
                                width: parent.width
                                Text {
                                    width: parent.width / 2
                                    text: qsTr("km/h")
                                    color: center.mute
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                }
                                Text {
                                    width: parent.width / 2
                                    text: qsTr("kN")
                                    color: center.mute
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                            ListView {
                                id: points
                                width: parent.width
                                height: parent.height - 72
                                clip: true
                                model: col.modelData.pts || []
                                delegate: Rectangle {
                                    id: row
                                    required property var modelData
                                    required property int index
                                    width: points.width
                                    height: 26
                                    radius: 6
                                    color: col.pick === index
                                           ? Qt.rgba(1, 0.35, 0.12, 0.28)
                                           : "transparent"

                                    Row {
                                        anchors.fill: parent
                                        spacing: 2
                                        Item {
                                            width: 12
                                            height: parent.height
                                            Rectangle {
                                                anchors.centerIn: parent
                                                width: 3
                                                height: 12
                                                radius: 1
                                                color: center.mute
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.SizeVerCursor
                                                drag.target: row
                                                drag.axis: Drag.YAxis
                                                drag.minimumY: -row.height * row.index
                                                drag.maximumY: points.height
                                                onPressed: col.pick = row.index
                                                onReleased: {
                                                    var shift = Math.round(row.y / row.height)
                                                    row.y = 0
                                                    if (shift !== 0)
                                                        bridge.movePoint(col.modelData.n, row.index, row.index + shift)
                                                }
                                            }
                                        }
                                        Cell {
                                            width: (parent.width - 14) / 2
                                            height: parent.height
                                            cell: row.modelData.kmh
                                            onCommit: function(text) {
                                                bridge.editPoint(col.modelData.n, row.index, 0, text)
                                            }
                                            onActiveFocusChanged: if (activeFocus) {
                                                col.pick = row.index
                                                bridge.focusNotch(col.modelData.n)
                                            }
                                        }
                                        Cell {
                                            width: (parent.width - 14) / 2
                                            height: parent.height
                                            cell: row.modelData.kn
                                            onCommit: function(text) {
                                                bridge.editPoint(col.modelData.n, row.index, 1, text)
                                            }
                                            onActiveFocusChanged: if (activeFocus) {
                                                col.pick = row.index
                                                bridge.focusNotch(col.modelData.n)
                                            }
                                        }
                                    }
                                }
                            }
                            Row {
                                width: parent.width
                                spacing: 4
                                RaiseButton {
                                    width: (parent.width - 4) / 2
                                    height: 28
                                    label: "+"
                                    onClicked: bridge.addPoint(col.modelData.n)
                                }
                                RaiseButton {
                                    width: (parent.width - 4) / 2
                                    height: 28
                                    label: qsTr("−")
                                    onClicked: bridge.delPoint(col.modelData.n, col.pick)
                                }
                            }
                        }
                    }
                }
            }
        }

        Row {
            id: tools
            anchors.top: notchFlick.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            height: 32
            spacing: 8

            RaiseButton {
                width: 118
                height: 32
                label: qsTr("Resistance")
                accent: !!center.bag.resist
                onClicked: bridge.setResist(!center.bag.resist)
            }
            SunkField {
                width: 168
                height: 32
                label: qsTr("km/h")
                value: center.bag.maxKmh || ""
                onEdited: function(text) { bridge.setGraphMax(text, center.bag.maxKn || "80") }
            }
            SunkField {
                width: 140
                height: 32
                label: qsTr("kN")
                value: center.bag.maxKn || ""
                onEdited: function(text) { bridge.setGraphMax(center.bag.maxKmh || "120", text) }
            }
            RaiseButton {
                width: 64
                height: 32
                label: qsTr("Fit")
                onClicked: bridge.fitGraph()
            }
            Text {
                width: Math.max(40, tools.width - 118 - 168 - 140 - 64 - 32)
                height: 32
                text: qsTr("Drag points on the graph · Ctrl snap 10 · Shift adds to the selection")
                color: center.mute
                font.pixelSize: 11
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }

        Item {
            id: graphWell
            anchors.top: tools.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            onXChanged: tuner.place()
            onYChanged: tuner.place()
            onWidthChanged: tuner.place()
            onHeightChanged: tuner.place()

            Rectangle {
                anchors.fill: parent
                radius: 12
                color: bridge.dark ? "#161a1e" : "#e8ebf0"
            }

            TeGraph {
                anchors.fill: parent
                anchors.margins: 4
            }
        }
    }

    component TeGraph: Item {
        id: plot

        property real padL: 44
        property real padR: 14
        property real padT: 14
        property real padB: 28
        property real maxKmh: Math.max(1, center.numOr(center.bag.maxKmh, 120))
        property real maxKn: Math.max(1, center.numOr(center.bag.maxKn, 80))
        property var picks: ([])
        property int dragN: -1
        property int dragI: -1
        property real dragKmh: 0
        property real dragKn: 0
        property bool dragging: false

        function plotW() { return Math.max(1, width - padL - padR) }
        function plotH() { return Math.max(1, height - padT - padB) }
        function xOf(kmh) { return padL + (Math.max(0, kmh) / maxKmh) * plotW() }
        function yOf(kn) { return padT + plotH() - (Math.max(0, kn) / maxKn) * plotH() }
        function kmhOf(px) { return Math.max(0, Math.min(maxKmh, ((px - padL) / plotW()) * maxKmh)) }
        function knOf(py) { return Math.max(0, Math.min(maxKn, ((padT + plotH() - py) / plotH()) * maxKn)) }

        function snap(v, step) {
            return Math.round(v / step) * step
        }

        function hit(mx, my) {
            var best = null
            var bestD = 12 * 12
            var notches = center.bag.notches || []
            for (var n = 0; n < notches.length; ++n) {
                var col = notches[n]
                var pts = col.pts || []
                for (var i = 0; i < pts.length; ++i) {
                    var kmh = center.numOr(pts[i].kmh, 0)
                    var kn = center.numOr(pts[i].kn, 0)
                    if (dragging && dragN === col.n && dragI === i) {
                        kmh = dragKmh
                        kn = dragKn
                    }
                    var dx = xOf(kmh) - mx
                    var dy = yOf(kn) - my
                    var d = dx * dx + dy * dy
                    if (d <= bestD) {
                        bestD = d
                        best = { n: col.n, i: i, kmh: kmh, kn: kn }
                    }
                }
            }
            return best
        }

        function keyOf(n, i) { return n + ":" + i }
        function selected(n, i) {
            var k = keyOf(n, i)
            for (var p = 0; p < picks.length; ++p)
                if (picks[p] === k) return true
            return false
        }
        function setPick(n, i, add) {
            var k = keyOf(n, i)
            if (add) {
                if (!selected(n, i))
                    picks = picks.concat([k])
            } else {
                picks = [k]
            }
        }

        function paintSoon() { canvas.requestPaint() }

        Connections {
            target: bridge
            function onChanged() { plot.paintSoon() }
            function onLayoutChanged() { plot.paintSoon() }
        }
        onWidthChanged: paintSoon()
        onHeightChanged: paintSoon()
        onMaxKmhChanged: paintSoon()
        onMaxKnChanged: paintSoon()
        onDraggingChanged: paintSoon()
        onDragKmhChanged: if (dragging) paintSoon()
        onDragKnChanged: if (dragging) paintSoon()

        Canvas {
            id: canvas
            anchors.fill: parent
            antialiasing: true
            renderTarget: Canvas.FramebufferObject
            renderStrategy: Canvas.Cooperative

            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var w = width
                var h = height
                if (w < 8 || h < 8)
                    return

                ctx.fillStyle = bridge.dark ? "#161a1e" : "#e8ebf0"
                ctx.beginPath()
                ctx.roundedRect(0, 0, w, h, 10, 10)
                ctx.fill()

                var pw = plot.plotW()
                var ph = plot.plotH()
                ctx.save()
                ctx.beginPath()
                ctx.rect(plot.padL, plot.padT, pw, ph)
                ctx.clip()

                ctx.strokeStyle = bridge.dark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.08)"
                ctx.lineWidth = 1
                var gx = 8
                var gy = 6
                for (var i = 0; i <= gx; ++i) {
                    var x = plot.padL + (pw * i / gx)
                    ctx.beginPath()
                    ctx.moveTo(x, plot.padT)
                    ctx.lineTo(x, plot.padT + ph)
                    ctx.stroke()
                }
                for (var j = 0; j <= gy; ++j) {
                    var y = plot.padT + (ph * j / gy)
                    ctx.beginPath()
                    ctx.moveTo(plot.padL, y)
                    ctx.lineTo(plot.padL + pw, y)
                    ctx.stroke()
                }

                if (center.bag.resist) {
                    ctx.strokeStyle = bridge.dark ? "rgba(226,232,240,0.55)" : "rgba(71,85,105,0.7)"
                    ctx.lineWidth = 1.5
                    ctx.setLineDash([5, 4])
                    ctx.beginPath()
                    var mass = 40
                    var bags = center.bag.bags || {}
                    var massRows = bags.mass || []
                    for (var mi = 0; mi < massRows.length; ++mi) {
                        if (String(massRows[mi].k).toLowerCase().indexOf("mass") >= 0) {
                            mass = center.numOr(massRows[mi].v, mass)
                            break
                        }
                    }
                    var A = 0.6 + 0.012 * mass
                    var B = 0.045
                    var C = 0.00035
                    for (var s = 0; s <= 64; ++s) {
                        var kv = plot.maxKmh * s / 64
                        var rk = A + B * (kv / 10) + C * (kv * kv / 100)
                        var px = plot.xOf(kv)
                        var py = plot.yOf(rk)
                        if (s === 0) ctx.moveTo(px, py)
                        else ctx.lineTo(px, py)
                    }
                    ctx.stroke()
                    ctx.setLineDash([])
                }

                var notches = center.bag.notches || []
                for (var n = 0; n < notches.length; ++n) {
                    var col = notches[n]
                    var pts = col.pts || []
                    if (!pts.length)
                        continue
                    var focus = bridge.notchFocus === col.n
                    ctx.strokeStyle = col.color || "#94a3b8"
                    ctx.lineWidth = focus ? 2.6 : 1.5
                    ctx.globalAlpha = (bridge.notchFocus < 0 || focus) ? 1.0 : 0.35
                    ctx.beginPath()
                    for (var p = 0; p < pts.length; ++p) {
                        var kmh = center.numOr(pts[p].kmh, 0)
                        var kn = center.numOr(pts[p].kn, 0)
                        if (plot.dragging && plot.dragN === col.n && plot.dragI === p) {
                            kmh = plot.dragKmh
                            kn = plot.dragKn
                        }
                        var qx = plot.xOf(kmh)
                        var qy = plot.yOf(kn)
                        if (p === 0) ctx.moveTo(qx, qy)
                        else ctx.lineTo(qx, qy)
                    }
                    ctx.stroke()
                }
                ctx.globalAlpha = 1

                for (var n2 = 0; n2 < notches.length; ++n2) {
                    var col2 = notches[n2]
                    var pts2 = col2.pts || []
                    for (var p2 = 0; p2 < pts2.length; ++p2) {
                        var u = center.numOr(pts2[p2].kmh, 0)
                        var v = center.numOr(pts2[p2].kn, 0)
                        if (plot.dragging && plot.dragN === col2.n && plot.dragI === p2) {
                            u = plot.dragKmh
                            v = plot.dragKn
                        }
                        var sx = plot.xOf(u)
                        var sy = plot.yOf(v)
                        var on = plot.selected(col2.n, p2) || (bridge.notchFocus === col2.n)
                        var r = on ? 5.5 : 4
                        ctx.beginPath()
                        ctx.fillStyle = col2.color || "#94a3b8"
                        ctx.arc(sx, sy, r, 0, Math.PI * 2)
                        ctx.fill()
                        if (on) {
                            ctx.strokeStyle = bridge.dark ? "#fff" : "#111"
                            ctx.lineWidth = 1.2
                            ctx.stroke()
                        }
                    }
                }
                ctx.restore()

                ctx.fillStyle = center.mute
                ctx.font = "11px sans-serif"
                ctx.textAlign = "center"
                ctx.textBaseline = "top"
                for (var tx = 0; tx <= 4; ++tx) {
                    var tkmh = plot.maxKmh * tx / 4
                    ctx.fillText(tkmh.toFixed(0), plot.xOf(tkmh), plot.padT + ph + 8)
                }
                ctx.textAlign = "right"
                ctx.textBaseline = "middle"
                for (var ty = 0; ty <= 4; ++ty) {
                    var tkn = plot.maxKn * ty / 4
                    ctx.fillText(tkn.toFixed(0), plot.padL - 6, plot.yOf(tkn))
                }
                ctx.textAlign = "left"
                ctx.textBaseline = "top"
                ctx.fillText("km/h", plot.padL + pw - 34, plot.padT + ph + 8)
                ctx.save()
                ctx.translate(10, plot.padT + 8)
                ctx.rotate(-Math.PI / 2)
                ctx.textAlign = "right"
                ctx.fillText("kN", 0, 0)
                ctx.restore()
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: plot.dragging ? Qt.ClosedHandCursor : Qt.ArrowCursor

            onPressed: function(mouse) {
                var hit = plot.hit(mouse.x, mouse.y)
                if (!hit) {
                    if (!(mouse.modifiers & Qt.ShiftModifier))
                        plot.picks = []
                    plot.paintSoon()
                    return
                }
                bridge.focusNotch(hit.n)
                plot.setPick(hit.n, hit.i, !!(mouse.modifiers & Qt.ShiftModifier))
                plot.dragN = hit.n
                plot.dragI = hit.i
                plot.dragKmh = hit.kmh
                plot.dragKn = hit.kn
                plot.dragging = true
                plot.paintSoon()
            }
            onPositionChanged: function(mouse) {
                if (!plot.dragging)
                    return
                var kmh = plot.kmhOf(mouse.x)
                var kn = plot.knOf(mouse.y)
                if (mouse.modifiers & Qt.ControlModifier) {
                    kmh = plot.snap(kmh, 10)
                    kn = plot.snap(kn, 10)
                }
                plot.dragKmh = kmh
                plot.dragKn = kn
            }
            onReleased: function(mouse) {
                if (!plot.dragging)
                    return
                var kmh = plot.dragKmh
                var kn = plot.dragKn
                if (mouse.modifiers & Qt.ControlModifier) {
                    kmh = plot.snap(kmh, 10)
                    kn = plot.snap(kn, 10)
                }
                var n = plot.dragN
                var i = plot.dragI
                plot.dragging = false
                plot.dragN = -1
                plot.dragI = -1
                bridge.setPointXY(n, i, kmh.toFixed(2), kn.toFixed(2))
            }
            onCanceled: {
                plot.dragging = false
                plot.dragN = -1
                plot.dragI = -1
                plot.paintSoon()
            }
        }
    }

    component SimPage: Item {
        id: sim

        function place() {
            if (!visible || graphWell.width < 2 || graphWell.height < 2)
                return
            var p = graphWell.mapToItem(center.pageRoot(), 0, 0)
            bridge.placeGraph(p.x, p.y, graphWell.width, graphWell.height)
        }

        onVisibleChanged: place()
        Component.onCompleted: place()

        Text {
            id: title
            text: qsTr("Simulation preview")
            color: center.ink
            font.pixelSize: 16
            font.bold: true
        }

        Row {
            id: controls
            anchors.top: title.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            height: 32
            spacing: 6

            SunkField { width: 120; height: 32; label: "Mass t"; value: (center.bag.sim && center.bag.sim.mass) || ""; onEdited: function(text) { bridge.setSim("mass", text) } }
            SunkField { width: 100; height: 32; label: "Motors"; value: (center.bag.sim && center.bag.sim.motors) || ""; onEdited: function(text) { bridge.setSim("motors", text) } }
            SunkField { width: 110; height: 32; label: "Grade"; value: (center.bag.sim && center.bag.sim.grade) || ""; onEdited: function(text) { bridge.setSim("grade", text) } }
            SunkField { width: 120; height: 32; label: "Time s"; value: (center.bag.sim && center.bag.sim.duration) || ""; onEdited: function(text) { bridge.setSim("duration", text) } }
            SunkField { width: 96; height: 32; label: "Notch"; value: (center.bag.sim && center.bag.sim.notch) || ""; onEdited: function(text) { bridge.setSim("notch", text) } }
            SunkField { width: 110; height: 32; label: "Brake"; value: (center.bag.sim && center.bag.sim.brake) || ""; onEdited: function(text) { bridge.setSim("brake", text) } }
            RaiseButton {
                width: 110
                height: 32
                label: qsTr("Emergency")
                accent: center.bag.sim && center.bag.sim.emergency === "1"
                onClicked: bridge.setSim("emergency", (center.bag.sim && center.bag.sim.emergency === "1") ? "0" : "1")
            }
            RaiseButton {
                width: 132
                height: 32
                label: qsTr("Run")
                accent: true
                onClicked: bridge.runSim()
            }
        }

        Text {
            id: stats
            anchors.top: controls.bottom
            anchors.topMargin: 6
            anchors.left: parent.left
            anchors.right: parent.right
            text: (center.bag.sim && center.bag.sim.stats) || ""
            color: center.mute
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }

        Item {
            id: graphWell
            anchors.top: stats.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            onXChanged: sim.place()
            onYChanged: sim.place()
            onWidthChanged: sim.place()
            onHeightChanged: sim.place()

            Rectangle {
                anchors.fill: parent
                radius: 12
                color: bridge.dark ? "#161a1e" : "#e8ebf0"
            }
        }
    }

    component BagColumn: Item {
        id: bagCol
        property string bagName: ""
        property string title: ""
        property var rows: []
        property int pick: -1

        Rectangle {
            anchors.fill: parent
            radius: 12
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
        }
        Column {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 4
            Text {
                text: (typeof bagCol.title === "string" ? qsTr(bagCol.title) : bagCol.title)
                color: center.ink
                font.pixelSize: 13
                font.bold: true
            }
            ListView {
                id: list
                width: parent.width
                height: parent.height - 64
                clip: true
                model: bagCol.rows
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    required property int index
                    width: list.width
                    height: 26
                    radius: 6
                    color: bagCol.pick === index ? Qt.rgba(1, 0.35, 0.12, 0.28) : "transparent"
                    Row {
                        anchors.fill: parent
                        Cell {
                            width: parent.width * 0.55
                            height: parent.height
                            cell: row.modelData.k
                            horizontalAlignment: TextInput.AlignLeft
                            onCommit: function(text) { bridge.editParam(bagCol.bagName, row.modelData.k, 0, text) }
                            onActiveFocusChanged: if (activeFocus) bagCol.pick = row.index
                        }
                        Cell {
                            width: parent.width * 0.45
                            height: parent.height
                            cell: row.modelData.v
                            onCommit: function(text) { bridge.editParam(bagCol.bagName, row.modelData.k, 1, text) }
                            onActiveFocusChanged: if (activeFocus) bagCol.pick = row.index
                        }
                    }
                }
            }
            Row {
                width: parent.width
                spacing: 4
                RaiseButton {
                    width: 36
                    height: 28
                    label: "+"
                    onClicked: bridge.addParam(bagCol.bagName)
                }
                RaiseButton {
                    width: 36
                    height: 28
                    label: qsTr("−")
                    onClicked: {
                        if (bagCol.pick < 0 || bagCol.pick >= bagCol.rows.length)
                            return
                        bridge.delParam(bagCol.bagName, bagCol.rows[bagCol.pick].k)
                    }
                }
            }
        }
    }

    component ParamsPage: Item {
        id: params

        Text {
            id: title
            text: qsTr("Engine & air brake parameters")
            color: center.ink
            font.pixelSize: 16
            font.bold: true
        }
        Text {
            id: tip
            anchors.top: title.bottom
            anchors.topMargin: 2
            text: qsTr("Trainz ×1000 ≈ bar · 1 bar = 100 kPa · edit any pressure column")
            color: center.mute
            font.pixelSize: 11
        }

        Row {
            id: bags
            anchors.top: tip.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            height: Math.max(140, params.height * 0.38)
            spacing: 6

            BagColumn {
                width: (bags.width - 18) / 4
                height: bags.height
                bagName: "motor"
                title: qsTr("motor")
                rows: (center.bag.bags && center.bag.bags.motor) || []
            }
            BagColumn {
                width: (bags.width - 18) / 4
                height: bags.height
                bagName: "mass"
                title: qsTr("mass")
                rows: (center.bag.bags && center.bag.bags.mass) || []
            }
            BagColumn {
                width: (bags.width - 18) / 4
                height: bags.height
                bagName: "flowsize"
                title: qsTr("flowsize")
                rows: (center.bag.bags && center.bag.bags.flowsize) || []
            }
            BagColumn {
                width: (bags.width - 18) / 4
                height: bags.height
                bagName: "volume"
                title: qsTr("volume")
                rows: (center.bag.bags && center.bag.bags.volume) || []
            }
        }

        Item {
            id: press
            anchors.top: bags.bottom
            anchors.topMargin: 8
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            property int pick: -1

            Rectangle {
                anchors.fill: parent
                radius: 12
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
            }
            Column {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4
                Text {
                    text: qsTr("pressure")
                    color: center.ink
                    font.pixelSize: 13
                    font.bold: true
                }
                Row {
                    width: parent.width
                    Text { width: parent.width * 0.28; text: "Key"; color: center.mute; font.pixelSize: 10 }
                    Text { width: parent.width * 0.24; text: "Trainz"; color: center.mute; font.pixelSize: 10; horizontalAlignment: Text.AlignRight }
                    Text { width: parent.width * 0.24; text: "bar"; color: center.mute; font.pixelSize: 10; horizontalAlignment: Text.AlignRight }
                    Text { width: parent.width * 0.24; text: "kPa"; color: center.mute; font.pixelSize: 10; horizontalAlignment: Text.AlignRight }
                }
                ListView {
                    id: pressList
                    width: parent.width
                    height: parent.height - 64
                    clip: true
                    model: center.bag.pressure || []
                    delegate: Rectangle {
                        id: row
                        required property var modelData
                        required property int index
                        width: pressList.width
                        height: 26
                        radius: 6
                        color: press.pick === index ? Qt.rgba(1, 0.35, 0.12, 0.28) : "transparent"
                        Row {
                            anchors.fill: parent
                            Cell {
                                width: parent.width * 0.28
                                height: parent.height
                                cell: row.modelData.k
                                horizontalAlignment: TextInput.AlignLeft
                                onCommit: function(text) { bridge.editPressure(row.modelData.k, 0, text) }
                                onActiveFocusChanged: if (activeFocus) press.pick = row.index
                            }
                            Cell {
                                width: parent.width * 0.24
                                height: parent.height
                                cell: row.modelData.native
                                onCommit: function(text) { bridge.editPressure(row.modelData.k, 1, text) }
                                onActiveFocusChanged: if (activeFocus) press.pick = row.index
                            }
                            Cell {
                                width: parent.width * 0.24
                                height: parent.height
                                cell: row.modelData.bar
                                onCommit: function(text) { bridge.editPressure(row.modelData.k, 2, text) }
                                onActiveFocusChanged: if (activeFocus) press.pick = row.index
                            }
                            Cell {
                                width: parent.width * 0.24
                                height: parent.height
                                cell: row.modelData.kpa
                                onCommit: function(text) { bridge.editPressure(row.modelData.k, 3, text) }
                                onActiveFocusChanged: if (activeFocus) press.pick = row.index
                            }
                        }
                    }
                }
                Row {
                    spacing: 4
                    RaiseButton { width: 36; height: 28; label: "+"; onClicked: bridge.addPressure() }
                    RaiseButton {
                        width: 36
                        height: 28
                        label: qsTr("−")
                        onClicked: {
                            var rows = center.bag.pressure || []
                            if (press.pick < 0 || press.pick >= rows.length)
                                return
                            bridge.delPressure(rows[press.pick].k)
                        }
                    }
                }
            }
        }
    }
}
