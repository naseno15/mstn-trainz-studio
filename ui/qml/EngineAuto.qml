import QtQuick

// Auto Tune right dock. Logic stays on the hidden panel; this is the glass chrome.
Item {
    id: dock
    clip: true

    readonly property color ink: bridge.dark ? "#f2f4f8" : "#1d1d1f"
    readonly property color mute: bridge.dark ? "#8b93a1" : "#5c6570"
    property real footPad: 0

    function val(key) {
        var raw = bridge.autoJson
        if (!raw)
            return ""
        var bag = JSON.parse(raw)
        var v = bag[key]
        return v === undefined || v === null ? "" : String(v)
    }
    function onFlag(key) {
        return val(key) === "1"
    }

    GlassPlate {
        anchors.fill: parent
        anchors.leftMargin: 4
        visible: dock.width > 40
        dark: bridge.dark
        plateRadius: 16
        foot: 8

        Item {
            anchors.fill: parent

            Column {
                id: head
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 6
                Text {
                    text: bridge.autoKind === "air" ? "Air brake" : "Auto Tune"
                    color: dock.ink
                    font.pixelSize: 15
                    font.bold: true
                }
                Text {
                    width: parent.width
                    text: bridge.autoKind === "air"
                          ? "Pressures, reservoirs, and the decel cap. Preview then Apply."
                          : "TE generate · Davis resistance · Preview then Apply"
                    color: dock.mute
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                }
                Item {
                    id: tabStrip
                    width: parent.width
                    height: bridge.autoKind === "air" ? 0 : 40
                    visible: height > 0

                    Rectangle {
                        anchors.fill: parent
                        radius: 14
                        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.32 : 0.06)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
                    }
                    Rectangle {
                        id: tabPill
                        y: 4
                        height: 32
                        radius: 11
                        width: (tabStrip.width - 8) / 2
                        x: 4 + bridge.autoTab * width
                        color: "#ff5a1f"
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: 16
                            anchors.rightMargin: 16
                            anchors.topMargin: 1
                            height: 1
                            color: Qt.rgba(1, 1, 1, 0.55)
                        }
                        transform: Scale {
                            id: tabScale
                            origin.x: tabPill.width / 2
                            origin.y: tabPill.height / 2
                        }
                        Behavior on x {
                            NumberAnimation { duration: 260; easing.type: Easing.OutCubic }
                        }
                    }
                    SequentialAnimation {
                        id: tabPop
                        NumberAnimation { target: tabScale; properties: "xScale,yScale"; to: 1.04; duration: 90 }
                        NumberAnimation { target: tabScale; properties: "xScale,yScale"; to: 1.0; duration: 160; easing.type: Easing.OutCubic }
                    }
                    Row {
                        anchors.fill: parent
                        Item {
                            width: parent.width / 2
                            height: parent.height
                            Text {
                                anchors.centerIn: parent
                                text: "Generate"
                                color: bridge.autoTab === 0 ? "#ffffff" : dock.ink
                                font.pixelSize: 13
                                font.bold: bridge.autoTab === 0
                            }
                            TapHandler {
                                onTapped: {
                                    if (bridge.autoTab !== 0) {
                                        bridge.setAutoTab(0)
                                        tabPop.restart()
                                    }
                                }
                            }
                        }
                        Item {
                            width: parent.width / 2
                            height: parent.height
                            Text {
                                anchors.centerIn: parent
                                text: "Friction"
                                color: bridge.autoTab === 1 ? "#ffffff" : dock.ink
                                font.pixelSize: 13
                                font.bold: bridge.autoTab === 1
                            }
                            TapHandler {
                                onTapped: {
                                    if (bridge.autoTab !== 1) {
                                        bridge.setAutoTab(1)
                                        tabPop.restart()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Column {
                id: foot
                anchors.bottom: parent.bottom
                anchors.bottomMargin: dock.footPad
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: 8
                Text {
                    width: parent.width
                    text: bridge.autoSummary
                    color: dock.mute
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    visible: text.length > 0
                }
                Row {
                    width: parent.width
                    spacing: 8
                    RaiseButton {
                        width: (parent.width - 8) / 2
                        label: "Preview"
                        onClicked: bridge.previewAuto()
                    }
                    RaiseButton {
                        width: (parent.width - 8) / 2
                        label: "Apply"
                        accent: true
                        onClicked: bridge.applyAuto()
                    }
                }
            }

            Item {
                id: pager
                visible: bridge.autoKind !== "air"
                anchors.top: head.bottom
                anchors.bottom: foot.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 8
                anchors.bottomMargin: 8
                clip: true

                Item {
                    id: slide
                    width: pager.width * 2
                    height: pager.height
                    x: bridge.autoTab === 1 ? -pager.width : 0
                    Behavior on x {
                        NumberAnimation { duration: 280; easing.type: Easing.OutCubic }
                    }

            Flickable {
                width: pager.width
                height: pager.height
                contentHeight: pages.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: pages
                    width: parent.width
                    spacing: 10

                    AutoCard {
                        title: "Max Power"
                        FieldGrid {
                            AirField { label: "Power"; unit: dock.val("powerUnit").length > 0 ? dock.val("powerUnit") : "kW"; unitTap: true; value: dock.val("powerKw"); onEdited: bridge.setAutoField("powerKw", text); onUnitClicked: bridge.cyclePowerUnit() }
                            AirField { label: "Coeff"; value: dock.val("powerCoeff"); onEdited: bridge.setAutoField("powerCoeff", text) }
                        }
                    }
                    AutoCard {
                        title: "Max Speed"
                        FieldGrid {
                            AirField { label: "Speed"; unit: "km/h"; value: dock.val("speedKmh"); onEdited: bridge.setAutoField("speedKmh", text) }
                            AirField { label: "Coeff"; value: dock.val("speedCoeff"); onEdited: bridge.setAutoField("speedCoeff", text) }
                        }
                    }
                    AutoCard {
                        title: "Adhesion Limit"
                        FieldGrid {
                            AirField {
                                label: "Max TE"
                                unit: "kN"
                                value: dock.val("maxTe")
                                fieldEnabled: dock.onFlag("maxTeOn")
                                onEdited: bridge.setAutoField("maxTe", text)
                            }
                        }
                        CheckRow {
                            label: "Estimate from adhesion weight"
                            checked: dock.onFlag("estTe")
                            onToggled: bridge.setAutoField("estTe", checked ? "0" : "1")
                        }
                        FieldGrid {
                            AirField {
                                label: "Friction"
                                unit: "%"
                                value: dock.val("frictionPct")
                                fieldEnabled: dock.onFlag("fricOn")
                                onEdited: bridge.setAutoField("frictionPct", text)
                            }
                            AirField {
                                label: "Adhesion"
                                unit: "t"
                                value: dock.val("adhesionT")
                                fieldEnabled: dock.onFlag("fricOn")
                                onEdited: bridge.setAutoField("adhesionT", text)
                            }
                        }
                    }
                    AutoCard {
                        title: "Curve"
                        FieldGrid {
                            AirField { label: "Notch"; unit: "×"; value: dock.val("notchCoeff"); onEdited: bridge.setAutoField("notchCoeff", text) }
                            AirField { label: "Nodes"; value: dock.val("nodeCount"); onEdited: bridge.setAutoField("nodeCount", text) }
                        }
                        CheckRow { label: "Fit graph in window"; checked: dock.onFlag("fit"); onToggled: bridge.setAutoField("fit", checked ? "0" : "1") }
                        CheckRow { label: "Regenerate throttle curves"; checked: dock.onFlag("regen"); onToggled: bridge.setAutoField("regen", checked ? "0" : "1") }
                        Text {
                            width: parent.width
                            text: "TE = Power×308/Speed. Diesel coeff ~1–2, electric ~2–3. Uncheck regenerate to only update resistance."
                            color: dock.mute
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }

            Flickable {
                x: pager.width
                width: pager.width
                height: pager.height
                contentHeight: friction.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: friction
                    width: parent.width
                    spacing: 10
                    AutoCard {
                        title: "Engine"
                        FieldGrid {
                            AirField { label: "Mass"; unit: "t"; value: dock.val("engMass"); onEdited: bridge.setAutoField("engMass", text) }
                            AirField { label: "Area"; unit: "m²"; value: dock.val("engArea"); onEdited: bridge.setAutoField("engArea", text) }
                            ShapeRow { label: "Shape"; index: dock.val("engShape"); onPicked: bridge.setAutoField("engShape", String(next)) }
                            AirField { label: "Axles"; value: dock.val("engAxles"); onEdited: bridge.setAutoField("engAxles", text) }
                            AirField { label: "Fric"; value: dock.val("engFric"); onEdited: bridge.setAutoField("engFric", text) }
                        }
                    }
                    AutoCard {
                        title: "Cars"
                        FieldGrid {
                            AirField { label: "Count"; unit: "×"; value: dock.val("carCount"); onEdited: bridge.setAutoField("carCount", text) }
                            AirField { label: "Mass"; unit: "t"; value: dock.val("carMass"); onEdited: bridge.setAutoField("carMass", text) }
                            AirField { label: "Area"; unit: "m²"; value: dock.val("carArea"); onEdited: bridge.setAutoField("carArea", text) }
                            AirField { label: "Axles"; value: dock.val("carAxles"); onEdited: bridge.setAutoField("carAxles", text) }
                            ShapeRow { label: "Shape"; index: dock.val("carShape"); onPicked: bridge.setAutoField("carShape", String(next)) }
                            AirField { label: "Fric"; value: dock.val("carFric"); onEdited: bridge.setAutoField("carFric", text) }
                        }
                    }
                    AutoCard {
                        title: "Track & acceleration"
                        FieldGrid {
                            AirField { label: "Grade"; unit: "%"; value: dock.val("grade"); onEdited: bridge.setAutoField("grade", text) }
                            AirField { label: "From"; unit: "km/h"; value: dock.val("accelV0"); onEdited: bridge.setAutoField("accelV0", text) }
                            AirField { label: "To"; unit: "km/h"; value: dock.val("accelV1"); onEdited: bridge.setAutoField("accelV1", text) }
                            AirField { label: "Notch"; value: dock.val("accelNotch"); onEdited: bridge.setAutoField("accelNotch", text) }
                        }
                        CheckRow { label: "Show resistance overlay"; checked: dock.onFlag("showResist"); onToggled: bridge.setAutoField("showResist", checked ? "0" : "1") }
                    }
                }
            }
                }
            }

            Flickable {
                id: airDock
                visible: bridge.autoKind === "air"
                anchors.top: head.bottom
                anchors.bottom: foot.top
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.topMargin: 8
                anchors.bottomMargin: 8
                contentHeight: airCol.height
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: airCol
                    width: airDock.width
                    spacing: 10
                    AutoCard {
                        title: "Pressures"
                        FieldGrid {
                            AirField { label: "BP rel"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("bpRel"); onEdited: bridge.setAutoField("bpRel", text); onUnitClicked: bridge.cyclePressUnit() }
                            AirField { label: "BP ini"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("bpIni"); onEdited: bridge.setAutoField("bpIni", text); onUnitClicked: bridge.cyclePressUnit() }
                            AirField { label: "BP full"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("bpFull"); onEdited: bridge.setAutoField("bpFull", text); onUnitClicked: bridge.cyclePressUnit() }
                            AirField { label: "BC full"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("bcFull"); onEdited: bridge.setAutoField("bcFull", text); onUnitClicked: bridge.cyclePressUnit() }
                            AirField { label: "MR"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("mr"); onEdited: bridge.setAutoField("mr", text); onUnitClicked: bridge.cyclePressUnit() }
                            AirField { label: "MR start"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("mrStart"); onEdited: bridge.setAutoField("mrStart", text); onUnitClicked: bridge.cyclePressUnit() }
                            AirField { label: "BC start"; unit: dock.val("pressUnit"); unitTap: true; value: dock.val("bcStart"); onEdited: bridge.setAutoField("bcStart", text); onUnitClicked: bridge.cyclePressUnit() }
                        }
                        Text {
                            width: parent.width
                            text: "Tap the unit to switch kPa, bar, and psi. BP ini is the minimum reduction and is not written."
                            color: dock.mute
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            width: parent.width
                            visible: dock.val("pipeNote").length > 0
                            text: dock.val("pipeNote")
                            color: dock.mute
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    AutoCard {
                        title: "Reservoirs"
                        FieldGrid {
                            AirField { label: "MR"; unit: "L"; value: dock.val("volMr"); onEdited: bridge.setAutoField("volMr", text) }
                            AirField { label: "Aux"; unit: "L"; value: dock.val("volAux"); onEdited: bridge.setAutoField("volAux", text) }
                            AirField { label: "BC"; unit: "L"; value: dock.val("volBc"); onEdited: bridge.setAutoField("volBc", text) }
                            AirField { label: "Pipe"; unit: "L"; value: dock.val("volPipe"); onEdited: bridge.setAutoField("volPipe", text) }
                            AirField { label: "Ind BC"; unit: "L"; value: dock.val("volInd"); onEdited: bridge.setAutoField("volInd", text) }
                        }
                    }
                    AutoCard {
                        title: "Brake force"
                        FieldGrid {
                            AirField { label: "Ratio"; unit: "ratio"; value: dock.val("brakeRatio"); onEdited: bridge.setAutoField("brakeRatio", text) }
                            AirField { label: "Decel"; unit: "mm/s²"; value: dock.val("maxDecel"); onEdited: bridge.setAutoField("maxDecel", text) }
                        }
                        Text {
                            width: parent.width
                            text: "max-decel is mm/s², the same number as config.txt. 4500 mm/s² = 4.5 m/s². Not newtons. Ratio is brakeratio, a scale with no force unit."
                            color: dock.mute
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }
                    }
                    AutoCard {
                        title: "Flow rates"
                        CheckRow {
                            label: "Write train-pipe flows on Apply"
                            checked: dock.onFlag("advanced")
                            onToggled: bridge.setAutoField("advanced", checked ? "0" : "1")
                        }
                        FieldGrid {
                            AirField { label: "Comp"; unit: "rate"; value: dock.val("flowComp"); fieldEnabled: dock.onFlag("advanced"); onEdited: bridge.setAutoField("flowComp", text) }
                            AirField { label: "Vent"; unit: "rate"; value: dock.val("flowVent"); fieldEnabled: dock.onFlag("advanced"); onEdited: bridge.setAutoField("flowVent", text) }
                            AirField { label: "Release"; unit: "rate"; value: dock.val("flowRes"); fieldEnabled: dock.onFlag("advanced"); onEdited: bridge.setAutoField("flowRes", text) }
                            AirField { label: "Aux"; unit: "rate"; value: dock.val("flowAux"); fieldEnabled: dock.onFlag("advanced"); onEdited: bridge.setAutoField("flowAux", text) }
                            AirField { label: "BC fill"; unit: "rate"; value: dock.val("flowBc"); fieldEnabled: dock.onFlag("advanced"); onEdited: bridge.setAutoField("flowBc", text) }
                        }
                    }
                    AutoCard {
                        title: "Stop test"
                        FieldGrid {
                            AirField { label: "Speed"; unit: "km/h"; value: dock.val("speedKmh"); onEdited: bridge.setAutoField("speedKmh", text) }
                            AirField { label: "Mass"; unit: "t"; value: dock.val("massT"); onEdited: bridge.setAutoField("massT", text) }
                            AirField { label: "Grade"; unit: "%"; value: dock.val("grade"); onEdited: bridge.setAutoField("grade", text) }
                        }
                        CheckRow {
                            label: "Emergency"
                            checked: dock.onFlag("emergency")
                            onToggled: bridge.setAutoField("emergency", checked ? "0" : "1")
                        }
                        RaiseButton {
                            width: parent.width
                            label: "JNR 5 bar"
                            onClicked: bridge.presetAir()
                        }
                    }
                }
            }
        }
    }

    component FieldGrid: Grid {
        width: parent ? parent.width : 0
        columns: 2
        columnSpacing: 8
        rowSpacing: 8
    }

    component AirField: SunkField {
        stacked: true
        width: parent ? Math.max(0, (parent.width - 8) / 2) : 0
    }

    component AutoCard: Rectangle {
        property string title: ""
        default property alias body: inner.data
        width: parent ? parent.width : 0
        height: inner.height + 28
        radius: 12
        color: Qt.rgba(0, 0, 0, bridge.dark ? 0.28 : 0.05)
        border.width: 1
        border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.40)
        Column {
            id: inner
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 8
            spacing: 6
            Text {
                text: title
                color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
                font.pixelSize: 13
                font.bold: true
            }
        }
    }

    component CheckRow: Item {
        property string label: ""
        property bool checked: false
        signal toggled()
        width: parent ? parent.width : 0
        height: 22
        Rectangle {
            id: box
            width: 16
            height: 16
            anchors.verticalCenter: parent.verticalCenter
            radius: 4
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.40 : 0.08)
            border.width: 1
            border.color: checked ? "#ff5a1f" : Qt.rgba(1, 1, 1, bridge.dark ? 0.2 : 0.4)
            Rectangle {
                anchors.centerIn: parent
                width: 8
                height: 8
                radius: 2
                color: checked ? "#ff5a1f" : "transparent"
            }
        }
        Text {
            anchors.left: box.right
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: bridge.dark ? "#f2f4f8" : "#1d1d1f"
            font.pixelSize: 12
        }
        TapHandler { onTapped: parent.toggled() }
    }

    component ShapeRow: Item {
        property string label: ""
        property string index: "0"
        signal picked(int next)
        width: parent ? Math.max(0, (parent.width - 8) / 2) : 0
        height: 48
        Text {
            id: lab
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 14
            text: parent.label
            color: bridge.dark ? "#8b93a1" : "#5c6570"
            font.pixelSize: 11
            elide: Text.ElideRight
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: lab.bottom
            anchors.bottom: parent.bottom
            anchors.topMargin: 2
            radius: 8
            color: Qt.rgba(0, 0, 0, bridge.dark ? 0.38 : 0.08)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, bridge.dark ? 0.08 : 0.35)
            Text {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                text: {
                    var i = parseInt(index, 10)
                    if (isNaN(i) || i < 0 || i >= bridge.shapeNames.length)
                        return ""
                    return bridge.shapeNames[i]
                }
                color: bridge.dark ? "#f4f6fa" : "#1c1c1e"
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler {
                onTapped: {
                    var i = parseInt(index, 10)
                    if (isNaN(i))
                        i = 0
                    var n = bridge.shapeNames.length
                    picked(n > 0 ? (i + 1) % n : 0)
                }
            }
        }
    }
}
