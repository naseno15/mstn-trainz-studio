/* +===============================================================================================================================+ */
/* |                                                                                                                               | */
/* |  ███╗   ███╗███████╗████████╗███╗   ██╗    ██████╗ ██████╗  ██████╗ ██████╗ ██╗   ██╗ ██████╗████████╗██╗ ██████╗ ███╗   ██╗  | */
/* |  ████╗ ████║██╔════╝╚══██╔══╝████╗  ██║    ██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██║   ██║██╔════╝╚══██╔══╝██║██╔═══██╗████╗  ██║  | */
/* |  ██╔████╔██║███████╗   ██║   ██╔██╗ ██║    ██████╔╝██████╔╝██║   ██║██║  ██║██║   ██║██║        ██║   ██║██║   ██║██╔██╗ ██║  | */
/* |  ██║╚██╔╝██║╚════██║   ██║   ██║╚██╗██║    ██╔═══╝ ██╔══██╗██║   ██║██║  ██║██║   ██║██║        ██║   ██║██║   ██║██║╚██╗██║  | */
/* |  ██║ ╚═╝ ██║███████║   ██║   ██║ ╚████║    ██║     ██║  ██║╚██████╔╝██████╔╝╚██████╔╝╚██████╗   ██║   ██║╚██████╔╝██║ ╚████║  | */
/* |  ╚═╝     ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═══╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝  ╚═════╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝  | */
/* |																															   | */
/* |                						Copyright 2024-2025 All rights reserved.											   | */
/* |												Made by MSTN Team.                                                             | */
/* +===============================================================================================================================+ */

include "Library.gs"
include "multiplayergame.gs"
include "drivercharacter.gs"
include "interface.gs"
include "gs.gs"
include "MeshObject.gs"
include "ScenarioBehavior.gs"
include "SessionVariables.gs"
include "Browser.gs"
include "PropertyBrowser.gs"

include "World.gs"
include "World1.gs"

include "signal.gs"
include "constructors.gs"

include "DefaultLocomotiveCabin.gs"
include "locomotive.gs"
include "train.gs"
include "Vehicle.gs"

class mainlib isclass Library {};

///// ----- アルストムシステムの情報 ----- /////
class AlsthomSystemData isclass CabinData{

    public bool     userEmailToggle = false;
    public bool     isValidClient = true;
    public bool     failureSimulationEnabled = true;
    public float    lastKeyTime = 0.0f;
    public bool     transformerThreadRunning = false;
    public bool     showAdvancedView = false;
    public Browser  activeBrowser;
    public bool     isUIVisible = false;
    public float    next_UIRefresh_time = 0.0f;
    
    // -- Caterpillar Trend Detection -- //
    public float    prev_engine_temp = 75.0f;
    public float    prev_engine_oil_press = 450.0f;
    public float    prev_engine_speed = 0.0f;
    public float    last_trend_update_time = 0.0f;
    public int      trend_temp_status = 0;      // -1: Down, 0: Steady, 1: Up
    public int      trend_oil_status = 0;
    public int      trend_speed_status = 0;
    public bool     isAuthorized = false;
    
    public string   userName = "";
    public string   userEmail = "";
    public string   userKey = "";
    public string   userPurchaseDate = "";
    public string   userEncrypt = "";
    public string   userEncryptConfirm = "";
    
    ///// ----- 一般的なシステムの情報 (いっぱんてきな System のじょうほう) | 編集しない！ ----- /////
    public string prefix_Print = "MSTN Debug> ";
	public define int CAR_DERAILED = -1;
	public define int CAR_CENTER   =  0;
	public define int CAR_FRONT    =  1;
	public define int CAR_BACK     =  2;
	public define int CAR_SINGLE   =  3; // CAR_FRONT + CAR_BACK == CAR_SINGLE. Yes, this is intentional.

	public int      m_carPosition; // position of car in train - one of the options above
	public int      status;

	public bool     directionRelativeToTrain;
	public bool     DeRailed = false;
	public bool     flyShunting = true;
    public bool     runDM = true;
    public string   locoARN;
    public bool     isDebug = false;
    public bool     isTrailer = false;
    public string   savedBogeyAssetKey = "";
    public bool     bogeyManualMode = false;
    public string   bogeyManualSelection = "";
    
    // -- バンパ－の情報 (Bumperのじょうほう) | 編集しない -- //
	public string   meshPipe_status;
	public string   meshPipe_side;
	public string   meshPipe_cab;
	public int      meshPipe_type;

    public bool     cab1BpRight;
    public bool     cab1BpLeft;
    public bool     cab2BpRight;
    public bool     cab2BpLeft;

    ///// ----- ETCSシステムの情報 (ETCS System のじょうほう) | 編集しない! ----- /////
    public float    ETCSvolSound = 50;
    public float    ETCSbrightnessDmi = 50;
    public float    ETCSsignalTargetDistance, ETCSspeedDistanceBrake, ETCSspeedTargetDistance;
    public int      ETCScircularTarget, ETCScircularSpdLimit, ETCS_needleEvent, ETCS_timeIndication;
    public int      ETCSmaxspeed0, ETCSmaxspeed1, ETCSmaxspeed2, ETCSmaxspeed3;
    public int      etcsLevel = 1;
    public int      isETCSdmiPage = 0;
    public int      ETCSmodeSRspeed = 25;
    public int      ETCSmodeSRdistance = 500;
    public int      ETCSbrakeMode = 2;  // 0 - BC BRAKE | 1 - BP BRAKE | 2 - COMBINED
    public int      etcsSHmode = 30;
    public int      etcsMaxSpeed = 100;

    public string   etcsDriverId = "";
    public string   etcsTRNid = "";
    public string   etcsSRspeed = "";
    public string   etcsSRdistance = "";
    public string   etcsSignalType = "";
    public string   etcsModeIndication = "";

    public bool     etcs_system = false;

    public bool     etcsSetupLevel = false;
    public bool     etcsSetupAck = false;
    public bool     etcsSetup = false;
    public bool     ETCSmainStart = false;
    public bool     ETCSisEOApass = false;
    public bool     isETCSnonlead = false;
    public bool     isETCSisolation = false;
    public bool     isETCSfullSupervision = false;
    public bool     isETCSshunting = false;
    public bool     ETCSisolation = false;

    public bool     isETCSspeedoToggle = false;
    public bool     isETCSneedleIsYellow = false;
    public bool     isETCSneedleIsRed = false;
    public bool     ETCSfsShowTargetDistance = false;

    public bool     isETCSemer = false;
    public bool     isETCSpenaltyBrake = false;
    public bool     isETCSbrake = false;
    
    // -- Persistent References (Bridge between Cabin Instances) -- //
    public GSObject etcs_kernel_persistent;
    public float    etcsLastHeartbeat = 0.0;
    public float    etcsLoopOwner = 0.0;
    
    ///// ----- エンジンシステムの情報 (Engine System じょうほう) | 編集しない! ----- /////
    public bool     PhysicsEngine = true;
    public bool     PhysicsScheme = true;
	public float    PhysicsMaxTE;
	public float    PhysicsSandEff;
	public float    PhysicsWheelslip;

    public float    temp = 75.0f;
    public float    trainmass;
    public float    trainlength;
    public float    wagonmass;
    public float    wagonlength;
    public float    engine_oil_pressure = 450.0f;
    public float    engine_water_level = 100.0f;
    public bool     isHotWater = false;
    public bool     onTickingHot = false;
    public bool     isCoolingDown;
    public float    waterCapacity;
    public float    fuelCapacity;
    public float    sandCapacity;
    public 	float maxGainFactor = 0.0f;
	public float waterCoolingDown = 0.0f;
	public float heatGainRandomFactor = 1.0f;
    public float    factorTempWeather = 1.0f;
    public float    engine_temp = 75.0f;
    
    // -- User Heat/Cool Adjustments -- //
    public float    userHeatRateAdjustment = 0.0f; // 0.0 = Auto
    public float    userCoolRateAdjustment = 5.0f; // 5.0 = Standard
    public float    currentDynamicHeatMinutes = 1.0f;
    public float    maxHeatMinutesLimit = 20.0f; // Dynamic max based on engine
    
    ///// ----- アルストムに一般的な情報 (Alsthom にいっぱんてきなじょうほう) | 編集しない ----- /////
    public bool     isEngineOn;
	public bool     isStarted;
    public bool     isPreparing;
    public bool     brakeIsolationKey = false;
    public bool     brakeKeyCabInit = false;
    public bool     isFrontLocomotive;
    public bool     isCompressorWork = true;
    public bool     isWheelSlip;
    public bool     isOverchargeBP = false;
    public bool     callEngineStartEvent;
    public bool     callEngineStopEvent;
    public float    engine_speed;
    public float    engine_speed_vel = 0.0f;
    public float    factorEngine_speed = 1.0f;
    public int      engine_throttle;
    public float    engine_target_notch_32 = 0.0f;
    public float    engine_pwm_timer = 0.0f;
    public float    engine_flow_timer = 0.0f;
    public float    last_handwheel_pos = 0.0f;
    public int      last_handwheel_range = 0; // 0: N, 1: -, 2: H, 3: +
    public float    last_hw_dt_time = 0.0f;

    public bool     dvd_system = true;
    public bool     dvd_reset;
    public bool     dvd_test;

    public bool     fastSetup = false;
    public bool     consoleFastSetup = false;
    public int      keyMarkerlight;
    public int      keyHeadlight;
    public int      keyWiper;

    public bool     toggleMainEngine = false;
    public bool     alsthomPrimingStarted;
    public bool     alsthomTransformerStarted;
    public bool     alsthomPreStarted;
    public bool     alsthomFirstStart = true;
    public bool     alsthomPreShutdown = false;
    public bool     isCompSpeedup;

    public bool     haslerVisible = true;
    public bool     sirenMeshToggle = false;

    // -- Missing properties from original cabin -- //
    public bool     catPrelubeEvent;
    public bool     isQSDTripped;
    public int      timeBlinking;

    // -- 列車運転手メッシュの情報 (れっしゃうんてんしゅうMeshのじょうほう) | 編集しない -- //
    public bool     isDriver0;
    public bool     isDriver1;
    public bool     isDriver2;
    public bool     isDriver3;

    public int      overrideDriver0;
    public int      overrideDriver1;
    public int      overrideDriver2;
    public int      overrideDriver3;

    // -- キャビン変数の情報 (Cabinへんすうのじょうほう) | 編集しない -- //
    public int      enginePanelInt = 2;
    public bool     reverserIsCab1;
    public bool     reverserIsCab2;
    public bool     brakeKeyIsCab1;
    public bool     brakeKeyIsCab2;
    public bool     brakeKeyIsInit;
    public bool     resetHandWheel;
    
    // -- ハスラ－のシステム -- //
    public float    haslerOdometer;
    public float    haslerTimerCount = 0;
    public float    haslerTimerTick;
    public int      haslerSpeedLimiter = 90.f;
    public int      haslerRandColor = 0;
    public bool     haslerResetThrottle;

    // -- モ－タ－牽引な遮断の情報 (Motorけんいんなしゃだんのじょうほう) | 編集しない! -- //
    public bool     tm1 = true;
    public bool     tm2 = true;
    public bool     tm3 = true;
    public bool     tm4 = true;
    public bool     tm5 = true;
    public bool     tm6 = true;

    public bool     tm1Switch = true;
    public bool     tm2Switch = true;
    public bool     tm3Switch = true;
    public bool     tm4Switch = true;
    public bool     tm5Switch = true;
    public bool     tm6Switch = true;

    public bool     tm1shocked = false;
    public bool     tm2shocked = false;
    public bool     tm3shocked = false;
    public bool     tm4shocked = false;
    public bool     tm5shocked = false;
    public bool     tm6shocked = false;

    public bool     isTMshocked;
    public float    adjustedMaxTE;
    public int      tmShortCircuitCount = 0.0f;
    public int      altShortCircuitCount = 0.0f;
    public int      activeTractionMotor;

    // -- マスタ－コントロ－ル -- //
    public bool     etcs_isolation;
    public float    reverser_handle_insert_cab1;
    public float    reverser_handle_insert_cab2;
    public int      reverser_handle;
    public int      handwheel_throttle;
    public float    abv_handle;
    public float    ibv_handle;
    public float    abv_brake_current;
    public float    abv_brake_target;
    public float    brake_key_cab1;
    public float    brake_key_cab2;
    public float    console_wiper_valve_driver;
    public float    console_wiper_valve_codriver;

    // -- コンソ－ル -- //
    public bool     console_switch_compressor;
    public bool     console_switch_engine_room_light;
    public bool     console_switch_headlight_normal;
    public bool     console_switch_alarm_horn_cutout;
    public bool     console_switch_signal_lamp_test;
    public bool     console_switch_cab_lights;
    public bool     console_switch_desk_lights;
    public bool     console_switch_shunting_light_left;
    public bool     console_switch_shunting_light_right;
    public bool     console_switch_headlight_bright;
    public bool     console_switch_headlight_dimmer;

    public bool     console_siren_switch;

    // -- コンソ－ルの下 -- //
    public bool     underbrake_er_isolation = 1;
    public bool     underbrake_wiper_isolation = 1;
    public bool     underbrake_sand_isolation = true;
    public bool     underbrake_horn_isolation = true;
    public bool     console_emergency_valve;

    // -- キャタピラ－のコンソ－ル -- //
    public bool     console_caterpillar_switch_clear;
    public int      console_caterpillar_switch_mode;
    public int      console_caterpillar_switch_right_left;

    // -- 電気室でTMをカット -- //
    public float    engineroom_isolation_tm16;
    public float    engineroom_isolation_tm34;
    public float    engineroom_isolation_tm25;
    public float    engineroom_isolation_headlamp = 0;
    public float    engineroom_isolation_vigilance = 0;
    public float    engineroom_isolation_fuelpump = 1;

    public bool     engineroom_battery_switch = false;

    // -- 遮断器に電気室 -- //
    public int      ccchr_breaker;
    public int      cccpa_breaker;
    public int      ccc_breaker;
    public int      ccpc_breaker;
    public int      cclm_breaker;
    public int      cclc1_breaker;
    public int      cclc2_breaker;
    public int      ccpr1_breaker;
    public int      ccpr2_breaker;
    public int      ccce11_breaker;
    public int      ccce22_breaker;
    public int      ccv_breaker;
    public int      ccpgo_breaker;
    public int      engine_control_breaker;
    public int      djsoba_breaker;
    public int      djsqoht_breaker;
    public int      djsq10_breaker;
    public int      djstse_breaker;
    public int      djstsh_breaker;
    public int      etcs_power_breaker;
    public int      etcs_bypass_breaker;
    public int      ccstc_breaker;
    public int      ccpgr_breaker;
    public int      engineroom_breaker_etcs_leading = 1;
    public int      engineroom_breaker_etcs_cab_active = 1;

    public float    driverseat_right_cab1;
    public float    driverseat_left_cab1;
    public float    driverseat_right_cab2;
    public float    driverseat_left_cab2;

    public float    sunvisor_right_cab1;
    public float    sunvisor_left_cab1;
    public float    sunvisor_right_cab2;
    public float    sunvisor_left_cab2;

    public float    windows_left_cab1;
    public float    windows_right_cab1;
    public float    windows_left_cab2;
    public float    windows_right_cab2;

    public float    door_body_left_cab1;
    public float    door_body_right_cab1;
    public float    door_body_left_cab2;
    public float    door_body_right_cab2;

    public float    engine_room_left;
    public float    engine_room_right;

    public float    door_cab_left_cab1;
    public float    door_cab_right_cab1;
    public float    door_cab_left_cab2;
    public float    door_cab_right_cab2;

    // -- システムの健康状態 (System Health Status) -- //
    // 0: Normal | 1: Stuck ON | 2: Stuck OFF (Dead)
    public int h_cat_awth, h_cat_ctl, h_cat_efom, h_cat_eos, h_cat_ffdph, h_cat_imath, h_cat_opl;
    public int h_fl_lsd, h_fl_lqsd, h_fl_lsmh, h_fl_lspse, h_fl_lsqdi, h_fl_lse, h_fl_lspat, h_fl_lscpa;
    public int h_g_oil_pressure, h_gauge_rpm, h_gauge_oil;

    // -- Brake Air Sound State -- //
    public float    last_bp_press;
    public float    last_abv_handle;
    public int      brake_air_state = 0; // 0: Idle, 1: Start, 2: Loop, 3: Stop
    public int      brake_air_type = 0;  // 0: None, 1: Normal, 2: Emergency
    public float    brake_air_timer = 0.0f;
    public float    brake_air_loop_timer = 0.0f;
};