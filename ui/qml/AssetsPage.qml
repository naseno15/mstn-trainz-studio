import QtQuick

// Assets Tools stage. Center chrome is QML. Tables, editors, and canvases stay widgets in the well.
// Packages queue stays a widget in the sidebar well. This page paints depth + nav.
Item {
    id: root

    Chrome { id: chrome }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: bridge.dark ? "#1a2230" : "#eef1f6" }
            GradientStop { position: 1.0; color: bridge.dark ? "#0c0e12" : "#d5dbe3" }
        }
    }

    Item {
        id: stage
        property bool dockDrag: false
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 8
        anchors.bottomMargin: chrome.stageMargin

        AssetsSide {
            id: side
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

        Item {
            id: queueSlot
            anchors.left: side.left
            anchors.right: side.right
            anchors.top: side.top
            anchors.bottom: side.bottom
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            anchors.topMargin: side.headH
            anchors.bottomMargin: side.footH + side.footPad
            visible: bridge.showQueue

            function sync() {
                if (!bridge.showQueue || width < 8 || height < 8) {
                    bridge.placeQueue(0, 0, 0, 0)
                    return
                }
                var p = mapToItem(root, 0, 0)
                bridge.placeQueue(p.x, p.y, width, height)
            }
            onXChanged: sync()
            onYChanged: sync()
            onWidthChanged: sync()
            onHeightChanged: sync()
            Component.onCompleted: sync()
        }

        Item {
            id: dockSlot
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: bridge.dockOn ? bridge.dockW : 0
            property bool widthReady: false
            Behavior on width {
                enabled: dockSlot.widthReady && !stage.dockDrag
                NumberAnimation { duration: 280; easing.type: Easing.OutCubic }
            }

            AssetsViewer {
                id: viewerChrome
                anchors.fill: parent
                visible: bridge.viewerOn && dockSlot.width > 40
            }

            AssetsDock {
                id: formChrome
                anchors.fill: parent
                visible: bridge.formOn && dockSlot.width > 40
            }

            GlassPlate {
                anchors.fill: parent
                visible: !bridge.viewerOn && !bridge.formOn && dockSlot.width > 40
                dark: bridge.dark
                plateRadius: 16
                foot: 8
            }

            Item {
                id: previewSlot
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                anchors.topMargin: viewerChrome.padTop
                anchors.bottomMargin: viewerChrome.padBottom
                visible: bridge.viewerOn && dockSlot.width > 40

                function sync() {
                    if (!visible || width < 8 || height < 8) {
                        bridge.placePreview(0, 0, 0, 0)
                        return
                    }
                    var p = mapToItem(root, 0, 0)
                    bridge.placePreview(p.x, p.y, width, height)
                }
                onXChanged: sync()
                onYChanged: sync()
                onWidthChanged: sync()
                onHeightChanged: sync()
                Component.onCompleted: sync()
            }

            Item {
                id: formToolSlot
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.top: parent.top
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                anchors.bottomMargin: 16
                anchors.topMargin: formChrome.padTop
                visible: bridge.formTool && dockSlot.width > 40

                function sync() {
                    if (!visible || width < 8 || height < 8) {
                        bridge.placeFormTool(0, 0, 0, 0)
                        return
                    }
                    var p = mapToItem(root, 0, 0)
                    bridge.placeFormTool(p.x, p.y, width, height)
                }
                onXChanged: sync()
                onYChanged: sync()
                onWidthChanged: sync()
                onHeightChanged: sync()
                Component.onCompleted: sync()
            }

            function contentH() {
                if (width < 40)
                    return height
                var o = mapToItem(root, 0, 0)
                if (o.x + width <= nav.x + 8 || o.x >= nav.x + nav.width - 8)
                    return height
                return Math.max(40, height - chrome.contentInset(nav.height))
            }

            function sync() {
                var p = mapToItem(root, 0, 0)
                bridge.placeDock(p.x, p.y, width, contentH())
            }
            onXChanged: sync()
            onYChanged: sync()
            onWidthChanged: sync()
            onHeightChanged: sync()
            Component.onCompleted: {
                widthReady = true
                sync()
            }
        }

        Item {
            id: centerSlot
            anchors.left: side.right
            anchors.leftMargin: 8
            anchors.right: dockSlot.left
            anchors.rightMargin: dockSlot.width > 8 ? 12 : 0
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.bottomMargin: chrome.contentInset(nav.height)

            AssetsCenter {
                id: centerChrome
                anchors.fill: parent
            }

            Item {
                id: centerBody
                visible: bridge.centerKind === "page"
                anchors.fill: parent
                anchors.leftMargin: centerChrome.padSide
                anchors.rightMargin: centerChrome.padSide
                anchors.topMargin: centerChrome.padTop
                anchors.bottomMargin: centerChrome.padBottom

                function sync() {
                    if (!visible || width < 8 || height < 8) {
                        bridge.placeCenter(0, 0, 0, 0)
                        return
                    }
                    var p = mapToItem(root, 0, 0)
                    bridge.placeCenter(p.x, p.y, width, height)
                }
                onXChanged: sync()
                onYChanged: sync()
                onWidthChanged: sync()
                onHeightChanged: sync()
                Component.onCompleted: sync()
            }
        }

        MouseArea {
            z: 3
            x: side.width - 3
            y: 0
            width: 10
            height: parent.height
            cursorShape: Qt.SplitHCursor
            property real lastX: 0
            onPressed: lastX = mapToItem(stage, mouseX, 0).x
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                bridge.setSideW(side.width + (now - lastX))
                lastX = now
            }
        }

        MouseArea {
            z: 30
            enabled: bridge.dockOn && dockSlot.width > 40
            x: dockSlot.x - 10
            y: 0
            width: 16
            height: parent.height
            cursorShape: Qt.SplitHCursor
            preventStealing: true
            property real lastX: 0
            property real grabW: 0
            onPressed: {
                stage.dockDrag = true
                lastX = mapToItem(stage, mouseX, 0).x
                grabW = bridge.dockW
            }
            onPositionChanged: {
                if (!pressed)
                    return
                var now = mapToItem(stage, mouseX, 0).x
                bridge.setDockW(grabW - (now - lastX))
            }
            onReleased: stage.dockDrag = false
            onCanceled: stage.dockDrag = false
        }
    }

    FontLoader {
        id: mi
        source: bridge.iconFontUrl
    }

    Item {
        id: nav
        // Full bar, centered in the gap between the sidebars.
        // When the right dock opens and the gap is narrower than the bar, slide left so the bar stays clear of that dock.
        readonly property real laneLeft: stage.x + side.width + 8
        readonly property real laneRight: dockSlot.width > 8 ? (stage.x + dockSlot.x - 8) : (stage.x + stage.width - 8)
        anchors.bottom: parent.bottom
        anchors.bottomMargin: chrome.barMargin
        width: Math.min(root.width - 32, Math.max(420, cluster.width + 40))
        x: {
            var lane = laneRight - laneLeft
            var mid = laneLeft + (lane - width) / 2
            if (width > lane)
                mid = laneRight - width
            return Math.max(8, Math.min(mid, root.width - width - 8))
        }
        height: bridge.navTall ? 100 : 76
        z: 20
        // Dock width already eases. A second ease on x restarts every frame and stutters.

        GlassPlate {
            anchors.fill: parent
            dark: bridge.dark
            plateRadius: 28
            foot: 10
        }

        Item {
            id: cluster
            anchors.centerIn: parent
            width: leftWell.width + homeGap + homeWell.width + homeGap + rightWell.width
            height: bridge.navTall ? 68 : 48
            property int homeGap: bridge.navTall ? 18 : 14

            function findChip(page) {
                var i
                for (i = 0; i < leftRep.count; i++) {
                    var a = leftRep.itemAt(i)
                    if (a && a.pageKey === page)
                        return a
                }
                for (i = 0; i < rightRep.count; i++) {
                    var b = rightRep.itemAt(i)
                    if (b && b.pageKey === page)
                        return b
                }
                return null
            }

            function firstKey() {
                var chip = leftRep.count > 0 ? leftRep.itemAt(0) : null
                return chip ? chip.pageKey : ""
            }

            function chipRow(chip) {
                var i
                for (i = 0; i < leftRep.count; i++) {
                    if (leftRep.itemAt(i) === chip)
                        return leftRow
                }
                return rightRow
            }

            function placePill(page, animate) {
                var chip = findChip(page)
                if (!chip || chip.width < 8) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                var row = chipRow(chip)
                if (row.width < 40) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                var at = chip.mapToItem(cluster, 0, 0)
                var rowAt = row.mapToItem(cluster, 0, 0)
                // Row still at the pre-layout origin — accepting that parks the pill off the label.
                if (Math.abs(at.y - rowAt.y) > 1 || rowAt.y < 1) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                // A later chip stays at x 0 until the Row places it. That lands the pill on Mesh Lods.
                var firstInRow = row === leftRow
                        ? (leftRep.count > 0 && leftRep.itemAt(0) === chip)
                        : (rightRep.count > 0 && rightRep.itemAt(0) === chip)
                if (!firstInRow && chip.x < 8) {
                    if (pillTries < 15)
                        pillRetry.restart()
                    return
                }
                pillTries = 0
                pill.visible = true
                if (!animate) {
                    if (pillSliding)
                        return
                    pill.x = at.x
                    pill.y = at.y + 4
                    pill.width = chip.width
                    pill.height = Math.max(28, chip.height - 8)
                    return
                }
                pillSliding = true
                slideX.to = at.x
                slideY.to = at.y + 4
                slideW.to = chip.width
                slideH.to = Math.max(28, chip.height - 8)
                slideX.start()
                slideY.start()
                slideW.start()
                slideH.start()
            }

            property int pillTries: 0
            property bool pillSliding: false
            Timer {
                id: pillRetry
                interval: 40
                repeat: false
                onTriggered: {
                    cluster.pillTries += 1
                    cluster.placePill(bridge.page, false)
                }
            }

            Rectangle {
                id: leftWell
                z: 0
                y: 2
                width: Math.max(80, leftRow.width + 12)
                height: parent.height - 4
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }

            Rectangle {
                id: homeWell
                z: 3
                x: leftWell.width + cluster.homeGap
                y: 2
                width: bridge.navTall ? 52 : 48
                height: parent.height - 4
                radius: 16
                color: homeH.hovered ? Qt.rgba(1, 0.35, 0.16, 0.35) : Qt.rgba(0, 0, 0, bridge.dark ? 0.22 : 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.16 : 0.55)

                Text {
                    z: 2
                    anchors.centerIn: parent
                    text: bridge.homeLabel
                    font.family: mi.name.length > 0 ? mi.name : bridge.iconFont
                    font.pixelSize: bridge.navTall ? 24 : 22
                    color: homeH.hovered ? "#ff5a1f" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                }
                HoverHandler { id: homeH }
                TapHandler { onTapped: bridge.goHome() }
            }

            Rectangle {
                id: rightWell
                z: 0
                x: homeWell.x + homeWell.width + cluster.homeGap
                y: 2
                width: Math.max(80, rightRow.width + 12)
                height: parent.height - 4
                radius: 16
                color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
            }

            Rectangle {
                id: pill
                z: 1
                visible: false
                y: 6
                x: 6
                width: 100
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
                onFinished: {
                    cluster.pillSliding = false
                    cluster.placePill(bridge.page, false)
                    pillPop.restart()
                }
            }
            NumberAnimation { id: slideY; target: pill; property: "y"; duration: 280; easing.type: Easing.OutCubic }
            NumberAnimation { id: slideW; target: pill; property: "width"; duration: 280; easing.type: Easing.OutCubic }
            NumberAnimation { id: slideH; target: pill; property: "height"; duration: 280; easing.type: Easing.OutCubic }
            SequentialAnimation {
                id: pillPop
                NumberAnimation { target: pillScale; properties: "xScale,yScale"; to: 1.06; duration: 120; easing.type: Easing.OutCubic }
                NumberAnimation { target: pillScale; properties: "xScale,yScale"; to: 1.0; duration: 200; easing.type: Easing.OutBack }
            }

            component NavChip: Item {
                property string pageKey: ""
                property string label: ""
                property int chipW: 96
                readonly property bool hot: bridge.page === pageKey
                width: chipW
                height: label.indexOf("\n") >= 0 ? 60 : 44
                z: 2
                Text {
                    z: 2
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 4
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    text: label
                    color: hot ? "#ffffff" : (bridge.dark ? "#f4f6fa" : "#1c1c1e")
                    font.pixelSize: 12
                    font.bold: hot
                }
                HoverHandler { id: chipH }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 4
                    radius: 10
                    z: -1
                    color: (!hot && chipH.hovered) ? Qt.rgba(1, 1, 1, bridge.dark ? 0.10 : 0.45) : "transparent"
                }
                TapHandler { onTapped: bridge.setPage(pageKey) }
            }

            // Declared after the pill. Its Scale layer would otherwise cover these labels.
            Row {
                id: leftRow
                z: 3
                x: leftWell.x + (leftWell.width - width) / 2
                y: leftWell.y + (leftWell.height - height) / 2
                spacing: 0
                onXChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onYChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onWidthChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                Repeater {
                    id: leftRep
                    model: cluster.leftModel
                    delegate: NavChip {
                        required property var modelData
                        pageKey: modelData.key
                        label: modelData.label
                        chipW: modelData.w
                    }
                }
            }

            Row {
                id: rightRow
                z: 3
                x: rightWell.x + (rightWell.width - width) / 2
                y: rightWell.y + (rightWell.height - height) / 2
                spacing: 0
                onXChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onYChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                onWidthChanged: if (!cluster.pillSliding) Qt.callLater(function() { cluster.placePill(bridge.page, false) })
                Repeater {
                    id: rightRep
                    model: cluster.rightModel
                    delegate: NavChip {
                        required property var modelData
                        pageKey: modelData.key
                        label: modelData.label
                        chipW: modelData.w
                    }
                }
            }

            property string tracked: bridge.page + "|" + bridge.suite
            property string leftRaw: bridge.leftNavJson
            property string rightRaw: bridge.rightNavJson
            property var leftModel: []
            property var rightModel: []
            onLeftRawChanged: {
                try { leftModel = JSON.parse(leftRaw) }
                catch (e) { leftModel = [] }
            }
            onRightRawChanged: {
                try { rightModel = JSON.parse(rightRaw) }
                catch (e) { rightModel = [] }
            }
            property bool slideArmed: false
            onTrackedChanged: if (slideArmed) {
                pillTries = 0
                Qt.callLater(function() { placePill(bridge.page, true) })
            }
            Component.onCompleted: Qt.callLater(function() {
                cluster.onLeftRawChanged()
                cluster.onRightRawChanged()
                placePill(bridge.page, false)
                slideArmed = true
            })
        }
    }

    Connections {
        target: bridge
        function onChanged() {
            queueSlot.sync()
            dockSlot.sync()
            previewSlot.sync()
            formToolSlot.sync()
            centerBody.sync()
            centerChrome.syncWells()
        }
    }
}
