import QtQuick
import QtQuick.Layouts

Item {
    id: root

    property bool popupOpen: false

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#9aa3b2" : "#5c6570"
    readonly property color edge: Qt.rgba(1, 1, 1, 0.2)

    component Btn: Rectangle {
        id: b
        property string label: ""
        property bool accent: false
        property bool active: false
        signal clicked()
        implicitWidth: lab.implicitWidth + 24
        implicitHeight: 30
        radius: 8
        color: b.accent || b.active ? "#ff5a1f" : (hv.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent")
        border.width: b.accent || b.active ? 0 : 1
        border.color: Qt.rgba(1, 1, 1, 0.2)
        Text {
            id: lab
            anchors.centerIn: parent
            text: b.label
            color: b.accent || b.active ? "#ffffff" : (bridge.dark ? "#f2f4f8" : "#1d1d1f")
            font.pixelSize: 13
        }
        HoverHandler { id: hv }
        TapHandler { onTapped: b.clicked() }
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1a2230" : "#eef1f6" }
            GradientStop { position: 1.0; color: bridge.dark ? "#161b24" : "#d5dbe3" }
        }
    }

    DropZone {
        anchors.fill: parent
        onDropped: function (drop) {
            var urls = []
            for (var i = 0; i < drop.urls.length; ++i)
                urls.push(String(drop.urls[i]))
            bridge.dropUrls(urls)
            drop.acceptProposedAction()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        // ---- left sidebar: clips ----
        GlassPlate {
            dark: bridge.dark
            plateRadius: 16
            Layout.preferredWidth: 250
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8
                LogoMark {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 68
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: bridge.title
                    color: root.ink
                    font.pixelSize: 15
                    font.bold: true
                }
                Text { text: bridge.clipsTitle; color: root.ink; font.pixelSize: 13; font.bold: true }
                ListView {
                    id: clips
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: bridge.clips
                    currentIndex: bridge.current
                    spacing: 2
                    delegate: Rectangle {
                        required property string modelData
                        required property int index
                        width: clips.width
                        height: 28
                        radius: 8
                        color: index === clips.currentIndex ? "#ff5a1f" : (rowHover.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40) : "transparent")
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            anchors.right: parent.right
                            text: modelData
                            color: index === clips.currentIndex ? "#ffffff" : root.ink
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        HoverHandler { id: rowHover }
                        TapHandler { onTapped: bridge.selectClip(index) }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: bridge.dropHint
                    color: root.mute
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 10
                        color: openHover.hovered ? "#ff5a1f" : (bridge.dark ? "#2a3340" : "#ffffff")
                        Text {
                            anchors.centerIn: parent
                            text: bridge.openGlyph
                            font.family: bridge.iconFont
                            font.pixelSize: 20
                            color: openHover.hovered ? "#ffffff" : "#ff5a1f"
                        }
                        HoverHandler { id: openHover }
                        TapHandler { onTapped: bridge.browse() }
                    }
                    Btn { label: bridge.ffmpegBtn; onClicked: bridge.pickFfmpeg() }
                    Item { Layout.fillWidth: true }
                    Btn { label: bridge.homeLabel; onClicked: bridge.goHome() }
                }
            }
        }

        // ---- center column ----
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            // toolbar
            GlassPlate {
                dark: bridge.dark
                plateRadius: 16
                foot: 6
                Layout.fillWidth: true
                Layout.preferredHeight: 100
                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Btn { label: bridge.playLabel; active: bridge.playLabel === "Playing"; onClicked: bridge.togglePlay() }
                        Btn { label: bridge.stopLabel; onClicked: bridge.stop() }
                        Btn { label: bridge.loopLabel; active: bridge.loopLabel === "Loop: On"; onClicked: bridge.toggleLoop() }
                        Btn { label: bridge.fixLabel; accent: true; onClicked: bridge.fix() }
                        Text { text: "Vol"; color: root.mute; font.pixelSize: 12 }
                        Item {
                            id: gainSlider
                            Layout.preferredWidth: 140
                            Layout.preferredHeight: 30
                            readonly property real frac: (bridge.gainDb + 24) / 36
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 4; radius: 2; color: root.edge }
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width * gainSlider.frac; height: 4; radius: 2; color: "#ff5a1f" }
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                x: (parent.width - width) * gainSlider.frac
                                width: 14; height: 14; radius: 7; color: "#ffffff"; border.color: "#ff5a1f"
                            }
                            MouseArea {
                                anchors.fill: parent
                                function setFrom(mx) { bridge.gainDb = -24 + 36 * Math.max(0, Math.min(1, mx / width)) }
                                onPressed: function (m) { setFrom(m.x) }
                                onPositionChanged: function (m) { if (pressed) setFrom(m.x) }
                                onDoubleClicked: bridge.gainDb = 0
                            }
                        }
                        Text { text: (bridge.gainDb > 0 ? "+" : "") + bridge.gainDb.toFixed(1) + " dB"; color: root.ink; font.pixelSize: 12; Layout.preferredWidth: 56 }
                        Btn {
                            id: devBtn
                            Layout.maximumWidth: 240
                            label: "Out: " + (bridge.devices[bridge.deviceIndex] || "")
                            onClicked: {
                                var p = devBtn.mapToItem(root, 0, devBtn.height + 4)
                                pop.x = Math.max(8, Math.min(p.x, root.width - pop.width - 8))
                                pop.y = p.y
                                root.popupOpen = !root.popupOpen
                            }
                        }
                        Rectangle {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 30
                            radius: 8
                            color: "#ff5a1f"
                            Text {
                                anchors.centerIn: parent
                                text: bridge.saveGlyph
                                font.family: bridge.iconFont
                                font.pixelSize: 16
                                color: "#ffffff"
                            }
                            TapHandler { onTapped: bridge.saveAs() }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Btn { label: bridge.setA; onClicked: bridge.setSlotA() }
                        Btn { label: bridge.setB; onClicked: bridge.setSlotB() }
                        Btn { label: bridge.playAB; accent: true; onClicked: bridge.playAB() }
                        Text { text: bridge.slots; color: root.mute; font.pixelSize: 12; elide: Text.ElideRight; Layout.maximumWidth: 360 }
                        Text { text: bridge.phase; color: "#ff5a1f"; font.pixelSize: 12 }
                        Text {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignRight
                            text: bridge.barTip + "   [Space] play/stop"
                            color: root.mute
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                GlassPlate {
                    dark: bridge.dark
                    plateRadius: 16
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        Text {
                            Layout.fillWidth: true
                            text: bridge.meta
                            color: root.mute
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        Item {
                            id: waveSlot
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            function report() {
                                if (root.popupOpen) {
                                    bridge.waveRect(0, 0, 0, 0)
                                    return
                                }
                                var p = mapToItem(root, 0, 0)
                                bridge.waveRect(p.x, p.y, width, height)
                            }
                            Connections { target: root; function onPopupOpenChanged() { waveSlot.report() } }
                            onWidthChanged: report()
                            onHeightChanged: report()
                            onXChanged: report()
                            onYChanged: report()
                            Component.onCompleted: report()
                        }
                        Text {
                            Layout.fillWidth: true
                            text: bridge.amp
                            color: root.mute
                            font.pixelSize: 12
                        }
                    }
                }

                GlassPlate {
                    dark: bridge.dark
                    plateRadius: 16
                    Layout.preferredWidth: 340
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        Text { text: bridge.qcTitle + " (whole track)"; color: root.ink; font.pixelSize: 13; font.bold: true }
                        Flickable {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            contentWidth: width
                            contentHeight: qcText.implicitHeight
                            clip: true
                            Text {
                                id: qcText
                                width: parent.width
                                text: bridge.qc
                                color: root.ink
                                font.pixelSize: 12
                                font.family: "Consolas"
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }

            // engine sound simulator (visible once an enginesound folder is dropped)
            GlassPlate {
                dark: bridge.dark
                plateRadius: 16
                foot: 6
                visible: bridge.engineOn
                Layout.fillWidth: true
                Layout.preferredHeight: bridge.engineOn ? 64 : 0
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    spacing: 8
                    Text { text: "Engine sim"; color: root.ink; font.pixelSize: 13; font.bold: true }
                    Btn { label: "Start"; accent: true; onClicked: bridge.engStart() }
                    Btn { label: "Notch -"; onClicked: bridge.engDown() }
                    Btn { label: "Notch +"; onClicked: bridge.engUp() }
                    Btn { label: "Stop engine"; onClicked: bridge.engStop() }
                    Text { text: bridge.engineText; color: "#ff5a1f"; font.pixelSize: 13; font.bold: true }
                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignRight
                        text: bridge.engineName
                        color: root.mute
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }

    // ---- output device dropdown (wave overlay hides while open) ----
    MouseArea {
        anchors.fill: parent
        z: 40
        visible: root.popupOpen
        onClicked: root.popupOpen = false
    }
    Rectangle {
        id: pop
        z: 41
        visible: root.popupOpen
        width: 320
        height: devCol.implicitHeight + 12
        radius: 10
        color: bridge.dark ? "#1b222d" : "#ffffff"
        border.color: root.edge
        Column {
            id: devCol
            anchors.fill: parent
            anchors.margins: 6
            spacing: 2
            Repeater {
                model: bridge.devices
                delegate: Rectangle {
                    required property string modelData
                    required property int index
                    width: devCol.width
                    height: 28
                    radius: 7
                    color: index === bridge.deviceIndex ? "#ff5a1f" : (dh.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.40) : "transparent")
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.right: parent.right
                        text: modelData
                        color: index === bridge.deviceIndex ? "#ffffff" : root.ink
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    HoverHandler { id: dh }
                    TapHandler { onTapped: { bridge.deviceIndex = index; root.popupOpen = false } }
                }
            }
        }
    }
}
