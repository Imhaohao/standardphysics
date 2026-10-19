use criterion::{Criterion, criterion_group, criterion_main};
use sp_bench::{APPLE_SAMPLES, apple_capture, apple_scene, flat_floor_mesh, repo_engine, synthetic_scene};
use sp_core::roomplan::import_captured_json;
use std::hint::black_box;

fn import(c: &mut Criterion) {
    let captures: Vec<String> = APPLE_SAMPLES.iter().map(|name| apple_capture(name)).collect();
    c.bench_function("import apple samples", |b| {
        b.iter(|| captures.iter().map(|json| import_captured_json(black_box(json)).unwrap().len()).sum::<usize>())
    });
}

fn evaluate_apple(c: &mut Criterion) {
    let mut engine = repo_engine();
    let scene = apple_scene();
    c.bench_function("evaluate_all apple samples", |b| {
        b.iter(|| {
            engine.set_scene(scene.clone());
            black_box(engine.evaluate_all())
        })
    });
    let room = scene.rooms[0].clone();
    engine.set_scene(scene);
    engine.evaluate_all();
    c.bench_function("update_room apple bedroom", |b| b.iter(|| black_box(engine.update_room(room.clone()))));
}

fn evaluate_synthetic(c: &mut Criterion) {
    let mut engine = repo_engine();
    let scene = synthetic_scene(9);
    c.bench_function("evaluate_all synthetic 10 rooms", |b| {
        b.iter(|| {
            engine.set_scene(scene.clone());
            black_box(engine.evaluate_all())
        })
    });
    let room = scene.rooms[5].clone();
    engine.set_scene(scene.clone());
    engine.evaluate_all();
    c.bench_function("update_room synthetic 10 rooms", |b| b.iter(|| black_box(engine.update_room(room.clone()))));
    let mesh = flat_floor_mesh(&scene);
    engine.set_room_mesh("corridor", mesh);
    c.bench_function("evaluate_all synthetic 10 rooms with floor mesh", |b| {
        b.iter(|| {
            engine.set_scene(scene.clone());
            black_box(engine.evaluate_all())
        })
    });
}

criterion_group! {
    name = benches;
    config = Criterion::default().sample_size(20);
    targets = import, evaluate_apple, evaluate_synthetic
}
criterion_main!(benches);
