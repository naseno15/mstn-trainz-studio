import QtQuick

// One clearance for every studio page. Content sits this far above the floating bottom bar.
QtObject {
    readonly property int barMargin: 14
    readonly property int stageMargin: 8
    readonly property int gap: 18

    function contentInset(barHeight) {
        return barHeight + gap + (barMargin - stageMargin)
    }
}
