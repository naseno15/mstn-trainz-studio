import QtQuick

// Blender-style axis widget. Drag orbits. A click on an axis looks straight down it.
Item {
    id: gizmo
    width: 86
    height: 86

    readonly property var tips: {
        try { return JSON.parse(bridge.navJson) } catch (e) { return {"x": [1, 0, 0], "y": [0, -1, 0], "z": [0, 0, 1]} }
    }
    property int hot: -1
    property bool dragging: false
    property real lastX: 0
    property real lastY: 0

    function arm(i) {
        var key = i < 2 ? "x" : (i < 4 ? "y" : "z")
        var v = tips[key] || [0, 0, 0]
        var sign = (i % 2 === 0) ? 1 : -1
        return [sign * v[0], sign * v[1], v[2] * sign]
    }

    function hit(px, py) {
        var c = width * 0.5
        var best = -1
        var bestD = 10
        for (var i = 0; i < 6; ++i) {
            var a = arm(i)
            var len = (i % 2 === 0) ? 30 : 14
            var x = c + a[0] * len
            var y = c + a[1] * len
            var vx = x - c
            var vy = y - c
            var l2 = vx * vx + vy * vy
            var t = l2 < 1 ? 0 : Math.max(0, Math.min(1, ((px - c) * vx + (py - c) * vy) / l2))
            var sd = Math.hypot(px - (c + vx * t), py - (c + vy * t))
            var d = Math.min(Math.hypot(px - x, py - y), sd)
            if (d < bestD) {
                bestD = d
                best = i
            }
        }
        return best
    }

    Canvas {
        id: cv
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            var c = width * 0.5
            var order = [0, 2, 4]
            order.sort(function (a, b) { return gizmo.arm(a)[2] - gizmo.arm(b)[2] })
            var rgb = ["#f2382e", "#38d147", "#4780f2"]
            var names = ["X", "Y", "Z"]
            for (var n = 0; n < 3; ++n) {
                var i = order[n]
                var pos = gizmo.arm(i)
                var neg = gizmo.arm(i + 1)
                var col = rgb[i / 2]
                var hotPos = gizmo.hot === i
                var hotNeg = gizmo.hot === i + 1
                ctx.lineWidth = hotPos || hotNeg ? 3 : 2
                ctx.strokeStyle = col
                ctx.globalAlpha = 0.38
                ctx.beginPath()
                ctx.moveTo(c, c)
                ctx.lineTo(c + neg[0] * 14, c + neg[1] * 14)
                ctx.stroke()
                ctx.globalAlpha = hotPos ? 1 : 0.92
                ctx.beginPath()
                ctx.moveTo(c, c)
                ctx.lineTo(c + pos[0] * 30, c + pos[1] * 30)
                ctx.stroke()
                ctx.beginPath()
                ctx.fillStyle = col
                ctx.globalAlpha = hotNeg ? 0.9 : 0.45
                ctx.arc(c + neg[0] * 14, c + neg[1] * 14, 3.5, 0, Math.PI * 2)
                ctx.fill()
                ctx.beginPath()
                ctx.globalAlpha = 1
                ctx.arc(c + pos[0] * 30, c + pos[1] * 30, hotPos ? 7 : 5.5, 0, Math.PI * 2)
                ctx.fill()
                if (pos[2] > -0.15) {
                    ctx.globalAlpha = 1
                    ctx.fillStyle = "#f4f6f8"
                    ctx.font = "bold 11px sans-serif"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText(names[i / 2], c + pos[0] * 40, c + pos[1] * 40)
                }
            }
            ctx.globalAlpha = 1
        }
    }

    onTipsChanged: cv.requestPaint()
    onHotChanged: cv.requestPaint()

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        preventStealing: true
        cursorShape: gizmo.dragging ? Qt.ClosedHandCursor : (gizmo.hot >= 0 ? Qt.PointingHandCursor : Qt.OpenHandCursor)
        onPressed: function (m) {
            gizmo.lastX = m.x
            gizmo.lastY = m.y
            gizmo.dragging = false
            gizmo.hot = gizmo.hit(m.x, m.y)
        }
        onPositionChanged: function (m) {
            if (!pressed) {
                gizmo.hot = gizmo.hit(m.x, m.y)
                return
            }
            var dx = m.x - gizmo.lastX
            var dy = m.y - gizmo.lastY
            if (!gizmo.dragging && Math.hypot(dx, dy) < 3) return
            gizmo.dragging = true
            gizmo.lastX = m.x
            gizmo.lastY = m.y
            bridge.navDrag(dx, dy)
        }
        onReleased: {
            if (!gizmo.dragging && gizmo.hot >= 0) bridge.navAxis(gizmo.hot)
            gizmo.dragging = false
        }
        onExited: if (!pressed) gizmo.hot = -1
    }
}
