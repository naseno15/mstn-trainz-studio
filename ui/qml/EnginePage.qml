import QtQuick

// Engine Tuner stage. Center pages are QML. Matplotlib graphs sit in the graph well.
Item {
    id: root

    Chrome { id: chrome }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1a2230" : "#eef1f6" }
            GradientStop { position: 1.0; color: bridge.dark ? "#161b24" : "#d5dbe3" }
        }
    }

    Item {
        id: stage
        property bool layoutDrag: false
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 8
        anchors.bottomMargin: chrome.stageMargin

        EngineSide {
            id: side
            quiet: stage.layoutDrag
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: bridge.sideW
            footPad: {
                var o = mapToItem(root, 0, 0)
                if (o.x + width <= nav.x + 8 || o.x >= nav.x + nav.width - 8)
                    return 0
                return chrome.contentInset(nav.height)
            }
        }

        EngineAuto {
            id: autoDock
            quiet: stage.layoutDrag
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: bridge.autoOn ? Math.min(440, Math.max(280, parent.width * 0.36)) : 0
            footPad: {
                if (width < 40)
                    return 0
                var o = mapToItem(root, 0, 0)
                if (o.x + width <= nav.x + 8 || o.x >= nav.x + nav.width - 8)
                    return 0
                return chrome.contentInset(nav.height)
            }
            Behavior on width {
                NumberAnimation { duration: 280; easing.type: Easing.OutCubic }
            }
        }

        EngineCenter {
            id: editorSlot
            anchors.left: side.right
            anchors.leftMargin: 8
            anchors.right: autoDock.left
            anchors.rightMargin: autoDock.width > 8 ? 8 : 0
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: chrome.contentInset(nav.height)
        }

        MouseArea {
            z: 3
            enabled: !bridge.sideLocked
            x: side.width - 3
            y: 0
            width: 10
            height: parent.height
            cursorShape: Qt.SplitHCursor
            property real lastX: 0
            onPressed: {
                stage.layoutDrag = true
                lastX = mapToItem(stage, mouseX, 0).x
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                bridge.setSideW(side.width + (now - lastX))
                lastX = now
            }
            onReleased: stage.layoutDrag = false
            onCanceled: stage.layoutDrag = false
        }
    }

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    Item {
        id: nav
        // Center in the lane between the sidebar and the Auto Tune dock.
        readonly property real laneLeft: stage.x + side.width
        readonly property real laneRight: stage.x + stage.width - autoDock.width
        anchors.bottom: parent.bottom
        anchors.bottomMargin: chrome.barMargin
        width: Math.min(Math.max(160, laneRight - laneLeft - 16), 640)
        x: laneLeft + (laneRight - laneLeft - width) / 2
        height: 76
        z: 20

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            quiet: stage.layoutDrag
            plateRadius: 28
            foot: 10
        }

        Item {
            id: cluster
            anchors.centerIn: parent
            width: 560
            height: 48

            function chipFor(page) {
                if (page === "simulation")
                    return simChip
                if (page === "parameters")
                    return paramChip
                return tunerChip
            }

            function placePill(page, animate) {
                var chip = chipFor(page)
                var at = chip.mapToItem(cluster, 0, 0)
                if (!animate) {
                    pill.x = at.x
                    pill.width = chip.width
                    return
                }
                slideX.to = at.x
                slideW.to = chip.width
                slideX.start()
                slideW.start()
            }

            Rectangle {
                x: 0
                y: 2
                width: 236
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }
            Rectangle {
                x: 248
                y: 2
                width: 48
                height: 44
                radius: 16
                color: homeH.hovered ? Qt.rgba(1, 0.35, 0.16, 0.35) : Qt.rgba(0, 0, 0, bridge.dark ? 0.22 : 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.55)
            }
            Rectangle {
                x: 308
                y: 2
                width: 252
                height: 44
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }

            Rectangle {
                id: pill
                z: 1
                y: 6
                x: 6
                width: 112
                height: 36
                radius: 12
                color: "#ff5a1f"
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    anchors.topMargin: 1
                    height: 1
                    color: Qt.rgba(1, 1, 1, 0.55)
                }
                transform: Scale {
                    id: pillScale
                    origin.x: pill.width / 2
                    origin.y: pill.height / 2
                }
            }
            NumberAnimation {
                id: slideX
                target: pill
                property: "x"
                duration: 280
                easing.type: Easing.OutCubic
                onFinished: pillPop.restart()
            }
            NumberAnimation {
                id: slideW
                target: pill
                property: "width"
                duration: 280
                easing.type: Easing.OutCubic
            }
            SequentialAnimation {
                id: pillPop
                NumberAnimation {
                    target: pillScale
                    properties: "xScale,yScale"
                    to: 1.06
                    duration: 120
                    easing.type: Easing.OutCubic
                }
                NumberAnimation {
                    target: pillScale
                    properties: "xScale,yScale"
                    to: 1.0
                    duration: 200
                    easing.type: Easing.OutBack
                }
            }

            component NavChip: Item {
                property string key: ""
                property string label: ""
                property bool hot: false
                width: 112
                height: 48
                z: 2
                Text {
                    anchors.centerIn: parent
                    text: (typeof label === "string" ? qsTr(label) : label)
                    color: hot ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                    font.pixelSize: 13
                    font.bold: hot
                }
                HoverHandler { id: chipH }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 6
                    radius: 10
                    z: -1
                    color: (!hot && chipH.hovered) ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent"
                }
                TapHandler { onTapped: bridge.setPage(key) }
            }

            NavChip {
                id: tunerChip
                x: 6
                key: "tuner"
                label: (typeof bridge.tuner === "string" ? qsTr(bridge.tuner) : bridge.tuner)
                hot: bridge.page === "tuner"
            }
            NavChip {
                id: simChip
                x: 118
                key: "simulation"
                label: (typeof bridge.simulation === "string" ? qsTr(bridge.simulation) : bridge.simulation)
                hot: bridge.page === "simulation"
            }

            Item {
                x: 250
                y: 2
                width: 44
                height: 44
                z: 2
                Text {
                    anchors.centerIn: parent
                    text: (typeof bridge.homeLabel === "string" ? qsTr(bridge.homeLabel) : bridge.homeLabel)
                    font.family: mi.name.length > 0 ? mi.name : bridge.iconFont
                    font.pixelSize: 22
                    color: homeH.hovered ? "#ff5a1f" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                }
                HoverHandler { id: homeH }
                TapHandler { onTapped: bridge.goHome() }
            }

            NavChip {
                id: paramChip
                x: 314
                key: "parameters"
                label: (typeof bridge.parameters === "string" ? qsTr(bridge.parameters) : bridge.parameters)
                hot: bridge.page === "parameters"
            }

            Item {
                x: 432
                width: 122
                height: 48
                z: 2
                Text {
                    anchors.centerIn: parent
                    text: (typeof bridge.autoTune === "string" ? qsTr(bridge.autoTune) : bridge.autoTune)
                    font.pixelSize: 13
                    font.bold: bridge.autoOn
                    color: bridge.autoOn ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 6
                    radius: 10
                    z: -1
                    color: bridge.autoOn ? "#ff5a1f" : (autoH.hovered ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent")
                    border.width: bridge.autoOn ? 0 : 1
                    border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.14 : 0.40)
                }
                HoverHandler { id: autoH }
                TapHandler { onTapped: bridge.toggleAuto() }
            }

            property string tracked: bridge.page
            property bool slideArmed: false
            onTrackedChanged: if (slideArmed) placePill(tracked, true)
            Component.onCompleted: {
                placePill(bridge.page, false)
                slideArmed = true
            }
        }
    }
}
