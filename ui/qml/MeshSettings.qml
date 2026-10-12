import QtQuick

// Mesh Studio settings: viewport, lighting and camera. Mirrors the bridge state in sideJson.
Item {
    id: set

    readonly property var bag: {
        try { return JSON.parse(bridge.sideJson) } catch (e) { return {} }
    }
    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    readonly property color line: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
    readonly property var todNames: ["Dawn", "Day", "Dusk", "Night"]

    Flickable {
        id: scroller
        anchors.fill: parent
        anchors.margins: 22
        contentWidth: width
        contentHeight: col.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        MiddleScroll { flick: scroller }

        Column {
            id: col
            width: Math.min(scroller.width, 560)
            spacing: 14

            Text { text: qsTr("Settings"); color: set.ink; font.pixelSize: 22; font.bold: true }

            Heading { text: qsTr("Viewport") }
            Flow {
                width: parent.width
                spacing: 8
                Pill { label: qsTr("Ground"); on: set.bag.ground === true; onPicked: bridge.setChecked("ground", !on) }
                Pill { label: qsTr("Face orientation"); on: set.bag.face === true; onPicked: bridge.setChecked("face", !on) }
                Pill { label: qsTr("Reset camera"); on: false; onPicked: bridge.clickId("resetCam") }
            }

            Heading { text: qsTr("Environment") }
            Flow {
                width: parent.width
                spacing: 8
                Repeater {
                    model: (set.bag.env || {}).items || []
                    delegate: Pill {
                        required property string modelData
                        required property int index
                        label: modelData
                        on: index === (set.bag.env || {}).i
                        onPicked: bridge.setCombo("env", index)
                    }
                }
            }

            Heading { text: qsTr("Time of day") }
            Flow {
                width: parent.width
                spacing: 8
                Repeater {
                    model: set.todNames
                    delegate: Pill {
                        required property string modelData
                        required property int index
                        label: modelData
                        on: index === set.bag.tod
                        onPicked: bridge.setCombo("tod", index)
                    }
                }
            }

            Heading { text: qsTr("Lights") }
            Flow {
                width: parent.width
                spacing: 8
                Pill { label: qsTr("Sun"); on: set.bag.sun === true; onPicked: bridge.setChecked("sun", !on) }
                Repeater {
                    model: set.bag.lights || []
                    delegate: Pill {
                        required property var modelData
                        required property int index
                        label: modelData.t
                        on: modelData.on === true
                        onPicked: bridge.setChecked("light" + index, !on)
                    }
                }
            }

            Slide { lab: set.bag.azLab || ""; key: "az"; min: 0; max: 360; val: set.bag.az || 0 }
            Slide { lab: set.bag.elLab || ""; key: "el"; min: -10; max: 89; val: set.bag.el || 0 }
            Slide { lab: set.bag.intLab || ""; key: "sunInt"; min: 20; max: 500; val: set.bag.sunInt || 0 }
            Slide { lab: set.bag.emisLab || ""; key: "emis"; min: 0; max: 200; val: set.bag.emis || 0 }

            Heading { text: qsTr("Controls") }
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                color: set.mute
                font.pixelSize: 12
                lineHeight: 1.3
                text: qsTr("Drag: orbit · Right/Middle drag: pan · Wheel: zoom · Arrows / PgUp / PgDn: walk · R: reset camera · F3: FPS\nShift + click a part: select its material in the Mat tab")
            }
        }
    }

    component Heading: Text {
        color: set.mute
        font.pixelSize: 11
        font.bold: true
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 1
    }

    component Pill: Rectangle {
        id: pill
        property string label: ""
        property bool on: false
        signal picked()
        width: lab.implicitWidth + 28
        height: 32
        radius: 10
        color: on ? "#ff5a1f" : (hov.hovered ? Qt.rgba(1, 0.35, 0.12, 0.2) : Qt.rgba(0, 0, 0, bridge.dark ? 0.35 : 0.06))
        border.width: on ? 0 : 1
        border.color: set.line
        scale: tap.pressed ? 0.93 : (hov.hovered ? 1.06 : 1.0)
        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutBack; easing.overshoot: 2.5 } }
        Text {
            id: lab
            anchors.centerIn: parent
            text: pill.label
            color: pill.on ? "#ffffff" : set.ink
            font.pixelSize: 12
            font.bold: pill.on
        }
        HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: tap; onTapped: pill.picked() }
    }

    component Slide: Item {
        id: sl
        property string key: ""
        property string lab: ""
        property int min: 0
        property int max: 1
        property int val: 0
        readonly property real t: Math.max(0, Math.min(1, (val - min) / Math.max(1, max - min)))
        width: parent ? parent.width : 0
        height: 40
        Text { text: sl.lab; color: set.mute; font.pixelSize: 12; anchors.top: parent.top }
        Rectangle {
            id: track
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 4
            height: 6
            radius: 3
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.10)
            border.width: 1
            border.color: set.line
            Rectangle { width: Math.max(6, track.width * sl.t); height: 6; radius: 3; color: "#ff5a1f" }
            Rectangle {
                width: 16
                height: 16
                radius: 8
                anchors.verticalCenter: parent.verticalCenter
                x: Math.max(0, Math.min(track.width - width, track.width * sl.t - width / 2))
                color: bridge.dark ? "#f4f6fa" : "#ffffff"
                border.width: 1
                border.color: "#ff5a1f"
                scale: drag.pressed ? 1.3 : 1.0
                Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutBack; easing.overshoot: 2.5 } }
            }
            MouseArea {
                id: drag
                anchors.fill: parent
                anchors.margins: -8
                cursorShape: Qt.PointingHandCursor
                function apply(mx) {
                    bridge.setSlider(sl.key, Math.round(sl.min + Math.max(0, Math.min(1, (mx - 8) / track.width)) * (sl.max - sl.min)))
                }
                onPressed: function (m) { apply(m.x) }
                onPositionChanged: function (m) { if (pressed) apply(m.x) }
            }
        }
    }
}
