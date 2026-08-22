# The Complete Rust Guidebook: From Zero to Full-Stack Web Apps

> **No prior coding experience required.** This guidebook takes you step-by-step from knowing nothing about programming to building and deploying a full-stack web application entirely in Rust.

---

## Table of Contents

1. [Introduction & Setup](#1-introduction--setup)
2. [First Steps: Variables, Types, and Functions](#2-first-steps-variables-types-and-functions)
3. [Control Flow: Making Decisions](#3-control-flow-making-decisions)
4. [Data Structures: Structs, Enums, and Collections](#4-data-structures-structs-enums-and-collections)
5. [Ownership, Borrowing, and Lifetimes](#5-ownership-borrowing-and-lifetimes)
6. [Error Handling](#6-error-handling)
7. [Modules, Packages, and Cargo](#7-modules-packages-and-cargo)
8. [Traits and Generics](#8-traits-and-generics)
9. [Testing Your Code](#9-testing-your-code)
10. [Web Backend with Axum](#10-web-backend-with-axum)
11. [Database Integration with SQLx](#11-database-integration-with-sqlx)
12. [Frontend with Leptos](#12-frontend-with-leptos)
13. [Full-Stack Integration](#13-full-stack-integration)
14. [Deployment & Production](#14-deployment--production)
15. [Next Steps & Resources](#15-next-steps--resources)

---

## 1. Introduction & Setup

### What Is Rust?

Rust is a systems programming language that gives you **C and C++ level performance** while providing **memory safety guarantees** without a garbage collector. It was created by Graydon Hoare and is now maintained by the Rust Foundation.

**Why learn Rust?**
- **Blazing fast** — performance on par with C/C++
- **Memory safe** — no segfaults, no data races, no garbage collector
- **Fearless concurrency** — write multi-threaded code without fear
- **Excellent tooling** — Cargo (package manager), rustfmt (formatter), clippy (linter)
- **Growing ecosystem** — great for web backends, frontend (WASM), CLI tools, embedded, and more

### What Is "Full-Stack"?

"Full-stack" means you build **both the frontend (what users see)** and the **backend (server, database, API)**. In this guidebook, you'll use Rust for both:
- **Backend**: Axum web framework + SQLx for database access
- **Frontend**: Leptos framework (compiles to WebAssembly, runs in the browser)

### Installing Rust

We'll use **rustup**, the official Rust toolchain manager.

#### On Linux / macOS:

```bash
# Install rustup (includes rustc compiler and cargo)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Restart your shell or run:
source ~/.cargo/env
```

#### On Windows:

Download and run `rustup-init.exe` from [https://rustup.rs](https://rustup.rs), or use the same curl command in PowerShell.

#### Verify the installation:

```bash
rustc --version
cargo --version
```

You should see version numbers (e.g., `rustc 1.75.0`).

### Your First Rust Program

Create a file called `main.rs`:

```rust
fn main() {
    println!("Hello, world!");
}
```

Run it:

```bash
rustc main.rs
./main
```

You should see: `Hello, world!`

### Using Cargo (Rust's Build System and Package Manager)

Cargo is Rust's most important tool. It handles:
- **Compiling** your code
- **Managing dependencies** (libraries your project uses)
- **Running tests**
- **Building documentation**

Create a new project:

```bash
cargo new hello_rust
cd hello_rust
cargo run
```

This creates a project with:
- `Cargo.toml` — project configuration and dependencies
- `src/main.rs` — your source code

`cargo run` compiles and runs your program in one step.

### The Rust Philosophy

Rust's core principle is **zero-cost abstractions** — you get high-level safety and expressiveness without sacrificing performance. The compiler is strict, but it catches bugs at compile time that would crash your program at runtime in other languages.

> **Golden Rule**: If your Rust code compiles, it's very likely correct. The compiler is your friend, not your enemy.

---

## 2. First Steps: Variables, Types, and Functions

### Variables and Mutability

In Rust, **variables are immutable by default**. This is a core design choice that prevents bugs.

```rust
fn main() {
    let x = 5;        // immutable variable
    // x = 6;         // ERROR! cannot assign to immutable variable

    let mut y = 5;    // mutable variable (note the `mut` keyword)
    y = 6;            // This is fine!
    println!("y = {}", y);
}
```

**Why immutability by default?**
- The compiler can optimize better
- Fewer bugs — you don't accidentally change a value
- Thread-safe by default

### Shadowing

You can "shadow" a variable by declaring a new variable with the same name:

```rust
fn main() {
    let x = 5;
    let x = x + 1;    // shadows the previous x
    let x = x * 2;    // shadows again
    println!("x = {}", x);  // prints 12
}
```

Shadowing is different from mutability — the variable is still immutable, but you're creating a new binding.

### Data Types

Rust has two main categories of data types: **scalar** and **compound**.

#### Scalar Types

**Integers** — whole numbers:

```rust
let a: i32 = 100;     // signed 32-bit integer (can be negative)
let b: u32 = 42;      // unsigned 32-bit integer (always positive)
let c: i64 = 9999999999;  // 64-bit
let d: usize = 5;     // pointer-sized (depends on architecture)
```

| Size    | Signed | Unsigned |
|---------|--------|----------|
| 8-bit   | i8     | u8       |
| 16-bit  | i16    | u16      |
| 32-bit  | i32    | u32      |
| 64-bit  | i64    | u64      |
| 128-bit | i128   | u128     |
| arch    | isize  | usize    |

**Floating-point numbers** — decimals:

```rust
let pi: f64 = 3.14159;   // 64-bit float (default)
let e: f32 = 2.71828;    // 32-bit float
```

**Booleans** — true or false:

```rust
let is_rust_awesome: bool = true;
let is_cool = false;  // type inferred
```

**Characters** — single Unicode scalar values:

```rust
let letter: char = 'a';
let emoji: char = '😊';
let heart: char = '❤';
```

#### Compound Types

**Tuples** — fixed-size collections of different types:

```rust
let tup: (i32, f64, u8) = (42, 6.28, 1);

// Destructuring
let (x, y, z) = tup;
println!("x = {}, y = {}, z = {}", x, y, z);

// Access by index
println!("first = {}", tup.0);
```

**Arrays** — fixed-size collections of the same type:

```rust
let arr: [i32; 5] = [1, 2, 3, 4, 5];
let first = arr[0];     // 1
let second = arr[1];    // 2

// Array with default values
let zeros = [0; 10];    // [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
```

### Type Inference

Rust can often figure out the type for you:

```rust
let x = 42;        // i32 by default
let y = 3.14;      // f64 by default
let flag = true;   // bool
```

### Functions

Functions are the building blocks of Rust programs:

```rust
fn add(a: i32, b: i32) -> i32 {
    a + b  // no semicolon = return value (expression)
}

fn main() {
    let result = add(3, 4);
    println!("3 + 4 = {}", result);
}
```

**Key points about functions:**
- The `->` syntax specifies the return type
- The last expression (without semicolon) is the return value
- Use `return` for early returns

```rust
fn divide(a: f64, b: f64) -> f64 {
    if b == 0.0 {
        return 0.0;  // early return
    }
    a / b
}
```

### Expressions vs Statements

- **Statement**: an instruction that does something (e.g., `let x = 5;`)
- **Expression**: something that evaluates to a value (e.g., `5 + 3`)

```rust
fn main() {
    let x = 5;           // statement
    let y = {            // block expression
        let x = 3;
        x + 1             // this is the value of the block
    };
    println!("y = {}", y);  // prints 4
}
```

### Comments

```rust
// Single-line comment

/* Multi-line
   comment */

/// Documentation comment (for functions, structs, etc.)
fn my_function() {
    // ...
}
```

### Practice Exercises

1. Write a function that converts Celsius to Fahrenheit.
2. Write a function that returns the nth Fibonacci number.
3. Create variables of every basic type and print them.

---

---

## 3. Control Flow: Making Decisions

### If Expressions

Rust's `if` expressions let you branch your code:

```rust
fn main() {
    let number = 3;

    if number < 5 {
        println!("number is less than 5");
    } else if number == 5 {
        println!("number is exactly 5");
    } else {
        println!("number is greater than 5");
    }
}
```

**Important**: Unlike many languages, `if` is an expression in Rust, meaning it returns a value:

```rust
fn main() {
    let condition = true;
    let number = if condition { 5 } else { 6 };
    println!("number = {}", number);  // prints 5
}
```

### Loops

Rust has three kinds of loops: `loop`, `while`, and `for`.

#### `loop` — Infinite Loop

```rust
fn main() {
    let mut count = 0;

    let result = loop {
        count += 1;

        if count == 10 {
            break count * 2;  // break returns a value
        }
    };

    println!("result = {}", result);  // prints 20
}
```

You can also label loops for nested loops:

```rust
fn main() {
    'outer: loop {
        println!("outer loop");

        'inner: loop {
            println!("inner loop");
            break 'inner;  // breaks the inner loop
        }

        break 'outer;  // breaks the outer loop
    }
}
```

#### `while` — Conditional Loop

```rust
fn main() {
    let mut number = 3;

    while number != 0 {
        println!("{}!", number);
        number -= 1;
    }

    println!("Liftoff!");
}
```

#### `for` — Iterator Loop

`for` loops are the most common in Rust:

```rust
fn main() {
    let arr = [10, 20, 30, 40, 50];

    for element in arr {
        println!("element = {}", element);
    }

    // Range syntax
    for i in 1..=5 {  // 1 to 5 (inclusive)
        println!("{}!", i);
    }
}
```

### Match Expressions

`match` is Rust's most powerful control flow construct. It's like `switch` in other languages but much more expressive:

```rust
fn main() {
    let number = 3;

    match number {
        1 => println!("one"),
        2 => println!("two"),
        3 => println!("three"),
        4 | 5 => println!("four or five"),  // multiple patterns
        6..=10 => println!("between 6 and 10"),  // range
        _ => println!("something else"),  // catch-all (like default)
    }
}
```

`match` can also return values:

```rust
fn value_to_word(n: i32) -> &'static str {
    match n {
        0 => "zero",
        1 => "one",
        2 => "two",
        _ => "many",
    }
}
```

### Match with Enums (Preview)

We'll cover enums in detail later, but here's a preview of how powerful `match` is with them:

```rust
enum Coin {
    Penny,
    Nickel,
    Dime,
    Quarter,
}

fn value_in_cents(coin: Coin) -> u8 {
    match coin {
        Coin::Penny => 1,
        Coin::Nickel => 5,
        Coin::Dime => 10,
        Coin::Quarter => 25,
    }
}
```

### If Let Expressions

For simpler cases, `if let` is a shorthand for `match`:

```rust
fn main() {
    let some_value = Some(3);

    // Using match
    match some_value {
        Some(3) => println!("three"),
        _ => (),
    }

    // Using if let (cleaner)
    if let Some(3) = some_value {
        println!("three");
    }
}
```

### Practice Exercises

1. Write a program that prints the multiplication table from 1 to 10.
2. Write a function that takes an integer and returns "even" or "odd" using `if`.
3. Use a `for` loop to sum all numbers from 1 to 100.

---

